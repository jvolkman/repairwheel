"""Integration test: repair a wheel that links against non-allowlisted libraries.

This test builds a tiny shared library (``libtestdep_syslib.so``), compiles
a Python C extension that links against it, packages it into a wheel, and
runs ``repairwheel`` with ``--lib-dir`` pointing at the custom library.
Because the library is *not* on the manylinux allowlist, auditwheel will
graft it into the wheel's ``.libs/`` directory.

This exercises the full repair pipeline end-to-end on a real ELF binary,
including:
  - library discovery via ``load_ld_paths``  (issue #55 regression)
  - ELF patching / RPATH rewriting
  - manylinux tag assignment
  - the SBOM vendor patch (``tools/vendoring/patches/auditwheel.patch``)

Requirements (ubuntu-latest GitHub Actions runners satisfy all of these):
  - Linux x86_64 or aarch64
  - gcc / cc
  - Python development headers  (``python3-dev``)

The test is skipped automatically when any prerequisite is missing.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import textwrap
import zipfile
from base64 import urlsafe_b64encode
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------

_SKIP_REASON: str | None = None

if sys.platform != "linux":
    _SKIP_REASON = "system-library integration test is Linux-only"
elif platform.machine() not in ("x86_64", "aarch64"):
    _SKIP_REASON = f"unsupported machine: {platform.machine()}"
elif not shutil.which("cc") and not shutil.which("gcc"):
    _SKIP_REASON = "no C compiler found (need gcc or cc)"
elif not Path(sysconfig.get_path("include"), "Python.h").exists():
    _SKIP_REASON = "Python.h not found (need python3-dev)"

pytestmark = pytest.mark.skipif(_SKIP_REASON is not None, reason=_SKIP_REASON or "")


# ---------------------------------------------------------------------------
# C sources
# ---------------------------------------------------------------------------

# A trivial shared library that is NOT on the manylinux allowlist.
_DEP_SOURCE = textwrap.dedent("""\
    int dep_get_answer(void) { return 42; }
""")

# A Python C extension that links against our custom dep.
_EXT_SOURCE = textwrap.dedent("""\
    #define PY_SSIZE_T_CLEAN
    #include <Python.h>

    extern int dep_get_answer(void);

    static PyObject *
    syslib_test_answer(PyObject *self, PyObject *args)
    {
        return PyLong_FromLong(dep_get_answer());
    }

    static PyMethodDef methods[] = {
        {"answer", syslib_test_answer, METH_NOARGS, NULL},
        {NULL, NULL, 0, NULL}
    };

    static struct PyModuleDef moddef = {
        PyModuleDef_HEAD_INIT, "syslib_test", NULL, -1, methods
    };

    PyMODINIT_FUNC PyInit_syslib_test(void)
    {
        return PyModule_Create(&moddef);
    }
""")

_WHEEL_NAME = "syslibtest"
_WHEEL_VERSION = "0.0.1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cc() -> str:
    return shutil.which("cc") or shutil.which("gcc") or "cc"


def _build_dep(src_dir: Path, lib_dir: Path) -> Path:
    """Build libtestdep_syslib.so — a non-allowlisted shared library."""
    src_file = src_dir / "testdep_syslib.c"
    src_file.write_text(_DEP_SOURCE)
    out_file = lib_dir / "libtestdep_syslib.so"

    subprocess.check_call(
        [
            _cc(),
            "-shared",
            "-fPIC",
            "-Wl,-soname,libtestdep_syslib.so",
            "-o",
            str(out_file),
            str(src_file),
        ]
    )
    return out_file


def _build_ext(src_dir: Path, build_dir: Path, lib_dir: Path) -> Path:
    """Compile the C extension, linking against our custom dep and libpython.

    Linking against libpython exercises the ``remove_needed`` codepath
    in vendored repair.py (via ``LIBPYTHON_RE``): manylinux/musllinux
    wheels must NOT carry a libpython dependency.
    """
    ext_suffix = sysconfig.get_config_var("EXT_SUFFIX")
    out_file = build_dir / f"syslib_test{ext_suffix}"

    src_file = src_dir / "syslib_test.c"
    src_file.write_text(_EXT_SOURCE)

    include = sysconfig.get_path("include")
    libdir = sysconfig.get_config_var("LIBDIR") or "/usr/lib"

    # Determine the python library name (e.g. "python3.13")
    ldlibrary = sysconfig.get_config_var("LDLIBRARY") or ""
    # LDLIBRARY is like "libpython3.13.so" — extract "python3.13"
    pylib_match = re.match(r"lib(.+?)\.so", ldlibrary)
    pylib = pylib_match.group(1) if pylib_match else None

    link_args = [
        _cc(),
        "-shared",
        "-fPIC",
        f"-I{include}",
        f"-L{lib_dir}",
        f"-L{libdir}",
        "-Wl,--no-as-needed",
        "-ltestdep_syslib",
    ]
    if pylib:
        link_args.append(f"-l{pylib}")
    link_args += [
        f"-Wl,-rpath,{lib_dir}",
        "-o",
        str(out_file),
        str(src_file),
    ]

    subprocess.check_call(link_args)
    return out_file


def _make_wheel(ext_file: Path, out_dir: Path) -> Path:
    """Package the extension into a minimal wheel."""
    machine = platform.machine()
    py_ver = f"cp{sys.version_info[0]}{sys.version_info[1]}"
    plat_tag = f"linux_{machine}"
    tag = f"{py_ver}-{py_ver}-{plat_tag}"

    metadata = f"Metadata-Version: 2.1\nName: {_WHEEL_NAME}\nVersion: {_WHEEL_VERSION}\n"
    wheel_info = f"Wheel-Version: 1.0\nGenerator: test_syslib_integration\nRoot-Is-Purelib: false\nTag: {tag}\n"

    ext_name = ext_file.name
    dist_info = f"{_WHEEL_NAME}-{_WHEEL_VERSION}.dist-info"
    files: dict[str, bytes] = {
        f"{_WHEEL_NAME}/{ext_name}": ext_file.read_bytes(),
        f"{dist_info}/METADATA": metadata.encode(),
        f"{dist_info}/WHEEL": wheel_info.encode(),
        f"{dist_info}/top_level.txt": b"syslib_test\n",
    }

    record_path = f"{dist_info}/RECORD"
    records = []
    for fname, data in sorted(files.items()):
        digest = urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        records.append(f"{fname},sha256={digest},{len(data)}")
    records.append(f"{record_path},,")
    files[record_path] = "\n".join(records).encode()

    wheel_path = out_dir / f"{_WHEEL_NAME}-{_WHEEL_VERSION}-{tag}.whl"
    with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in sorted(files):
            zinfo = zipfile.ZipInfo(fname, date_time=(1980, 1, 1, 0, 0, 0))
            zinfo.external_attr = 0o100664 << 16
            zf.writestr(zinfo, files[fname])

    return wheel_path


def _run_repairwheel(wheel: Path, lib_dir: Path, out_dir: Path) -> Path:
    """Run ``python -m repairwheel`` on *wheel*, return the repaired path."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "repairwheel",
            str(wheel),
            "--output-dir",
            str(out_dir),
            "--lib-dir",
            str(lib_dir),
        ],
        env={**os.environ},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"repairwheel exited {result.returncode}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )

    results = list(out_dir.glob("*.whl"))
    assert len(results) == 1, f"Expected 1 repaired wheel, got {len(results)}"
    return results[0]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def syslib_env(tmp_path: Path) -> dict[str, Path]:
    """Build the custom dep, extension, and wheel. Return paths."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    wheel_dir = tmp_path / "wheels"
    wheel_dir.mkdir()
    out_dir = tmp_path / "repaired"
    out_dir.mkdir()

    _build_dep(src_dir, lib_dir)
    ext = _build_ext(src_dir, build_dir, lib_dir)
    wheel = _make_wheel(ext, wheel_dir)

    return {
        "lib_dir": lib_dir,
        "wheel": wheel,
        "out_dir": out_dir,
    }


@pytest.fixture()
def repaired_wheel(syslib_env: dict[str, Path]) -> Path:
    """Repair the wheel and return the repaired path."""
    return _run_repairwheel(
        syslib_env["wheel"],
        syslib_env["lib_dir"],
        syslib_env["out_dir"],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSyslibRepair:
    """Repair a wheel that links against a non-allowlisted shared library."""

    def test_repair_succeeds(self, repaired_wheel: Path):
        """repairwheel must complete without error."""
        assert repaired_wheel.exists()

    def test_repaired_wheel_bundles_dep(self, repaired_wheel: Path):
        """The repaired wheel must graft libtestdep_syslib into .libs/."""
        with zipfile.ZipFile(repaired_wheel) as zf:
            names = zf.namelist()

        libs_entries = [n for n in names if ".libs/" in n]
        dep_entries = [n for n in libs_entries if "testdep_syslib" in n]
        assert dep_entries, f"Expected libtestdep_syslib in .libs/, got: {libs_entries}"

    def test_repaired_wheel_has_manylinux_tag(self, repaired_wheel: Path):
        """The repaired wheel should be tagged manylinux, not plain linux."""
        assert "manylinux" in repaired_wheel.name, f"Expected manylinux tag in: {repaired_wheel.name}"

    def test_repair_is_idempotent(self, syslib_env: dict[str, Path], repaired_wheel: Path, tmp_path: Path):
        """repair(repair(wheel)) must produce a byte-identical wheel."""
        out2 = tmp_path / "repaired2"
        out2.mkdir()
        repaired2 = _run_repairwheel(repaired_wheel, syslib_env["lib_dir"], out2)

        assert (
            repaired_wheel.read_bytes() == repaired2.read_bytes()
        ), "Repairing an already-repaired wheel produced different output"

    def test_libpython_is_stripped(self, repaired_wheel: Path):
        """The repaired extension must NOT have a DT_NEEDED on libpython.

        Manylinux/musllinux wheels must not depend on libpython.
        The vendored repair code calls ``remove_needed`` to strip it.
        """
        with zipfile.ZipFile(repaired_wheel) as zf:
            ext_names = [n for n in zf.namelist() if n.endswith(sysconfig.get_config_var("EXT_SUFFIX"))]
            assert ext_names, "No extension found in wheel"

            import tempfile

            with tempfile.TemporaryDirectory() as td:
                td = Path(td)
                for ext_name in ext_names:
                    zf.extract(ext_name, td)
                    ext_path = td / ext_name
                    result = subprocess.run(
                        ["readelf", "-d", str(ext_path)],
                        capture_output=True,
                        text=True,
                    )
                    needed = [line for line in result.stdout.splitlines() if "(NEEDED)" in line]
                    for line in needed:
                        assert "libpython" not in line, f"libpython should have been stripped: {line}"


# ---------------------------------------------------------------------------
# End-to-end SBOM test (requires libbz2-dev + dpkg)
# ---------------------------------------------------------------------------

# libbz2 is NOT on the manylinux allowlist, so it will be grafted.
# dpkg can trace it back to a real package, so whichprovides succeeds
# and an SBOM is generated.
_BZ2_EXT_SOURCE = textwrap.dedent("""\
    #define PY_SSIZE_T_CLEAN
    #include <Python.h>
    #include <bzlib.h>

    static PyObject *
    bz2_test_version(PyObject *self, PyObject *args)
    {
        return PyUnicode_FromString(BZ2_bzlibVersion());
    }

    static PyMethodDef methods[] = {
        {"bz2version", bz2_test_version, METH_NOARGS, NULL},
        {NULL, NULL, 0, NULL}
    };

    static struct PyModuleDef moddef = {
        PyModuleDef_HEAD_INIT, "bz2_test", NULL, -1, methods
    };

    PyMODINIT_FUNC PyInit_bz2_test(void)
    {
        return PyModule_Create(&moddef);
    }
""")

_has_dpkg = shutil.which("dpkg") is not None
_has_bz2_dev = Path("/usr/include/bzlib.h").exists()
_has_libbz2 = any(
    Path(d).glob("libbz2.so*")
    for d in ("/usr/lib/x86_64-linux-gnu", "/usr/lib/aarch64-linux-gnu", "/usr/lib")
    if Path(d).is_dir()
)


def _build_bz2_ext(src_dir: Path, build_dir: Path) -> Path:
    """Build a C extension that links against libbz2."""
    ext_suffix = sysconfig.get_config_var("EXT_SUFFIX")
    out_file = build_dir / f"bz2_test{ext_suffix}"

    src_file = src_dir / "bz2_test.c"
    src_file.write_text(_BZ2_EXT_SOURCE)

    include = sysconfig.get_path("include")

    subprocess.check_call(
        [
            _cc(),
            "-shared",
            "-fPIC",
            f"-I{include}",
            "-Wl,--no-as-needed",
            "-lbz2",
            "-o",
            str(out_file),
            str(src_file),
        ]
    )
    return out_file


def _make_bz2_wheel(ext_file: Path, out_dir: Path) -> Path:
    """Package the bz2 extension into a minimal wheel."""
    machine = platform.machine()
    py_ver = f"cp{sys.version_info[0]}{sys.version_info[1]}"
    plat_tag = f"linux_{machine}"
    tag = f"{py_ver}-{py_ver}-{plat_tag}"

    wheel_name = "bz2test"
    wheel_version = "0.0.1"

    metadata = f"Metadata-Version: 2.1\nName: {wheel_name}\nVersion: {wheel_version}\n"
    wheel_info = f"Wheel-Version: 1.0\nGenerator: test_syslib_integration\nRoot-Is-Purelib: false\nTag: {tag}\n"

    ext_name = ext_file.name
    dist_info = f"{wheel_name}-{wheel_version}.dist-info"
    files: dict[str, bytes] = {
        f"{wheel_name}/{ext_name}": ext_file.read_bytes(),
        f"{dist_info}/METADATA": metadata.encode(),
        f"{dist_info}/WHEEL": wheel_info.encode(),
        f"{dist_info}/top_level.txt": b"bz2_test\n",
    }

    record_path = f"{dist_info}/RECORD"
    records = []
    for fname, data in sorted(files.items()):
        digest = urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        records.append(f"{fname},sha256={digest},{len(data)}")
    records.append(f"{record_path},,")
    files[record_path] = "\n".join(records).encode()

    wheel_path = out_dir / f"{wheel_name}-{wheel_version}-{tag}.whl"
    with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in sorted(files):
            zinfo = zipfile.ZipInfo(fname, date_time=(1980, 1, 1, 0, 0, 0))
            zinfo.external_attr = 0o100664 << 16
            zf.writestr(zinfo, files[fname])

    return wheel_path


@pytest.mark.skipif(not _has_dpkg, reason="SBOM test requires dpkg")
@pytest.mark.skipif(not _has_bz2_dev, reason="bzlib.h not found (need libbz2-dev)")
@pytest.mark.skipif(not _has_libbz2, reason="libbz2.so not found (need libbz2-1.0)")
class TestSbomEndToEnd:
    """End-to-end SBOM test using libbz2 (a real, non-allowlisted system lib).

    Because libbz2 is installed via the system package manager and is NOT
    on the manylinux allowlist, repairwheel will:
      1. Graft it into ``.libs/``
      2. Have ``whichprovides`` identify its owning package
      3. Generate an SBOM in ``.dist-info/sboms/``

    This verifies the full SBOM pipeline including the monkeypatch that
    prevents ``metadata.version('auditwheel')`` from crashing and
    rebrands the output as ``repairwheel``.
    """

    @pytest.fixture()
    def repaired_bz2_wheel(self, tmp_path: Path) -> Path:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        wheel_dir = tmp_path / "wheels"
        wheel_dir.mkdir()
        out_dir = tmp_path / "repaired"
        out_dir.mkdir()

        ext = _build_bz2_ext(src_dir, build_dir)
        wheel = _make_bz2_wheel(ext, wheel_dir)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "repairwheel",
                str(wheel),
                "--output-dir",
                str(out_dir),
            ],
            env={**os.environ},
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.fail(
                f"repairwheel exited {result.returncode}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
            )

        results = list(out_dir.glob("*.whl"))
        assert len(results) == 1
        return results[0]

    def test_repair_succeeds(self, repaired_bz2_wheel: Path):
        assert repaired_bz2_wheel.exists()

    def test_libbz2_is_bundled(self, repaired_bz2_wheel: Path):
        with zipfile.ZipFile(repaired_bz2_wheel) as zf:
            libs = [n for n in zf.namelist() if ".libs/" in n]
        bz2_libs = [n for n in libs if "libbz2" in n]
        assert bz2_libs, f"Expected libbz2 in .libs/, got: {libs}"

    def test_sbom_file_is_named_repairwheel(self, repaired_bz2_wheel: Path):
        """The SBOM file must be named repairwheel.cdx.json, not auditwheel."""
        with zipfile.ZipFile(repaired_bz2_wheel) as zf:
            names = zf.namelist()

        sbom_entries = [n for n in names if n.endswith(".cdx.json")]
        assert sbom_entries, f"No SBOM found in wheel; files: {names}"
        assert all(
            "repairwheel.cdx.json" in n for n in sbom_entries
        ), f"SBOM filename should be repairwheel.cdx.json, got: {sbom_entries}"
        assert not any("auditwheel.cdx.json" in n for n in names), "auditwheel.cdx.json should not exist in the wheel"

    def test_sbom_content_is_branded_repairwheel(self, repaired_bz2_wheel: Path):
        """The SBOM content must reference repairwheel, not auditwheel."""
        import json

        import repairwheel

        with zipfile.ZipFile(repaired_bz2_wheel) as zf:
            sbom_entry = next(n for n in zf.namelist() if n.endswith(".cdx.json"))
            sbom_data = json.loads(zf.read(sbom_entry))

        assert sbom_data["bomFormat"] == "CycloneDX"

        tools = sbom_data["metadata"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "repairwheel"
        assert tools[0]["version"] == repairwheel.__version__

        # Verify components include libbz2
        component_names = [c["name"] for c in sbom_data.get("components", [])]
        assert any("bz2" in n.lower() for n in component_names), f"Expected libbz2 in SBOM components, got: {component_names}"
