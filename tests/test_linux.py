"""Tests for Linux-specific repair logic."""

import sys
from pathlib import Path

import pytest

from repairwheel._vendor.auditwheel.libc import Libc
from repairwheel.linux import monkeypatch
from repairwheel.linux.repair import _detect_libc_and_musl_policy, _parse_platform_for_libc

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux-only tests")

# GNU strip/objcopy (BFD) older than 2.44 mis-lay out PT_LOAD segments that contain
# the PHDR table when it isn't at the start of the file, corrupting valid ELF files.
# See https://sourceware.org/bugzilla/show_bug.cgi?id=32946.
MIN_GNU_STRIP_VERSION = (2, 44)
# llvm-strip 18 breaks p_offset/p_vaddr congruence for a PT_LOAD that shares its
# offset with PT_PHDR (executables); 19+ handles it.
MIN_LLVM_STRIP_VERSION = (19,)


def _tool_version(path: str, marker: str) -> tuple[int, ...] | None:
    """Parse the version from `path --version` if its output contains `marker`."""
    import re
    import subprocess

    out = subprocess.run([path, "--version"], capture_output=True, text=True).stdout
    if marker not in out:
        return None
    pattern = r"GNU strip.*?(\d+)\.(\d+)" if marker == "GNU strip" else r"LLVM version (\d+)\.(\d+)"
    match = re.search(pattern, out)
    return tuple(int(g) for g in match.groups()) if match else None


def _find_llvm_strip() -> tuple[str, tuple[int, ...]] | None:
    """Return the newest llvm-strip on PATH, including versioned names like llvm-strip-20."""
    import glob
    import os
    import shutil

    paths = {p for p in [shutil.which("llvm-strip")] if p}
    for d in os.environ.get("PATH", "").split(os.pathsep):
        paths.update(p for p in glob.glob(os.path.join(d, "llvm-strip-[0-9]*")) if os.access(p, os.X_OK))
    found = [(v, p) for p in paths if (v := _tool_version(p, "LLVM version"))]
    return (max(found)[1], max(found)[0]) if found else None


@pytest.fixture(params=["gnu", "llvm"])
def strip_tool(request) -> str:
    """Path to a strip implementation that handles spec-valid relocated PHDR tables.

    Tool paths can be overridden with REPAIRWHEEL_TEST_GNU_STRIP / REPAIRWHEEL_TEST_LLVM_STRIP.
    If REPAIRWHEEL_TEST_REQUIRE_STRIP is set, a missing or too-old tool fails instead of skipping.
    """
    import os
    import shutil

    if request.param == "gnu":
        name, minimum, note = "GNU strip", MIN_GNU_STRIP_VERSION, " (binutils bug 32946)"
        path = os.environ.get("REPAIRWHEEL_TEST_GNU_STRIP") or shutil.which("strip")
        version = _tool_version(path, "GNU strip") if path else None
    else:
        name, minimum, note = "llvm-strip", MIN_LLVM_STRIP_VERSION, ""
        path = os.environ.get("REPAIRWHEEL_TEST_LLVM_STRIP")
        version = _tool_version(path, "LLVM version") if path else None
        if not path and (found := _find_llvm_strip()):
            path, version = found

    if version is None:
        reason = f"{name} not found"
    elif version < minimum:
        reason = f"{name} {'.'.join(map(str, version))} < {'.'.join(map(str, minimum))}{note}"
    else:
        return path

    if os.environ.get("REPAIRWHEEL_TEST_REQUIRE_STRIP"):
        pytest.fail(reason)
    pytest.skip(reason)


class TestPatchLoadLdPaths:
    """Verify the load_ld_paths monkeypatch matches auditwheel's expected signature."""

    def _get_patched_fn(self, lib_paths, use_sys_paths):
        monkeypatch.patch_load_ld_paths(lib_paths, use_sys_paths)
        import repairwheel._vendor.auditwheel.lddtree

        return repairwheel._vendor.auditwheel.lddtree.load_ld_paths

    def test_use_sys_paths_accepts_libc_arg(self):
        """With use_sys_paths=True, load_ld_paths(Libc.GLIBC) must work."""
        load_ld_paths = self._get_patched_fn([], use_sys_paths=True)
        result = load_ld_paths(Libc.GLIBC)
        assert isinstance(result, dict)
        assert "env" in result
        assert "conf" in result
        assert "interp" in result

    def test_no_sys_paths_accepts_libc_arg(self):
        """With use_sys_paths=False, load_ld_paths(Libc.GLIBC) must work."""
        load_ld_paths = self._get_patched_fn([], use_sys_paths=False)
        result = load_ld_paths(Libc.GLIBC)
        assert result == {"env": [], "conf": [], "interp": []}

    def test_no_sys_paths_includes_lib_paths(self):
        """User-provided lib paths appear in the env key."""
        lib_paths = [Path("/fake/lib1"), Path("/fake/lib2")]
        load_ld_paths = self._get_patched_fn(lib_paths, use_sys_paths=False)
        result = load_ld_paths(Libc.GLIBC)
        assert result["env"] == ["/fake/lib1", "/fake/lib2"]
        assert result["conf"] == []
        assert result["interp"] == []

    def test_use_sys_paths_prepends_lib_paths(self):
        """User-provided lib paths are prepended to the env list."""
        lib_paths = [Path("/fake/lib1")]
        load_ld_paths = self._get_patched_fn(lib_paths, use_sys_paths=True)
        result = load_ld_paths(Libc.GLIBC)
        assert result["env"][0] == "/fake/lib1"

    def test_accepts_none_libc(self):
        """load_ld_paths(None) must also work (libc is Optional)."""
        load_ld_paths = self._get_patched_fn([], use_sys_paths=True)
        result = load_ld_paths(None)
        assert isinstance(result, dict)
        assert "env" in result


class TestParsePlatformForLibc:
    """Unit tests for _parse_platform_for_libc."""

    def test_musllinux_1_1(self):
        result = _parse_platform_for_libc("musllinux_1_1_x86_64")
        assert result == (Libc.MUSL, "musllinux_1_1")

    def test_musllinux_1_2(self):
        result = _parse_platform_for_libc("musllinux_1_2_aarch64")
        assert result == (Libc.MUSL, "musllinux_1_2")

    def test_manylinux_2_17(self):
        result = _parse_platform_for_libc("manylinux_2_17_x86_64")
        assert result == (Libc.GLIBC, None)

    def test_manylinux2014(self):
        result = _parse_platform_for_libc("manylinux2014_x86_64")
        assert result == (Libc.GLIBC, None)

    def test_linux_plain(self):
        result = _parse_platform_for_libc("linux_x86_64")
        assert result is None

    def test_empty_string(self):
        result = _parse_platform_for_libc("")
        assert result is None


class TestDetectLibcAndMuslPolicy:
    """Unit tests for _detect_libc_and_musl_policy."""

    def test_auditwheel_plat_musllinux(self, monkeypatch):
        """AUDITWHEEL_PLAT=musllinux_1_2_x86_64 should detect MUSL."""
        monkeypatch.setenv("AUDITWHEEL_PLAT", "musllinux_1_2_x86_64")
        wheel = Path("pkg-1.0-cp38-cp38-linux_x86_64.whl")
        libc, musl_policy = _detect_libc_and_musl_policy(wheel)
        assert libc == Libc.MUSL
        assert musl_policy == "musllinux_1_2"

    def test_auditwheel_plat_manylinux(self, monkeypatch):
        """AUDITWHEEL_PLAT=manylinux_2_17_x86_64 should detect GLIBC."""
        monkeypatch.setenv("AUDITWHEEL_PLAT", "manylinux_2_17_x86_64")
        wheel = Path("pkg-1.0-cp38-cp38-linux_x86_64.whl")
        libc, musl_policy = _detect_libc_and_musl_policy(wheel)
        assert libc == Libc.GLIBC
        assert musl_policy is None

    def test_wheel_filename_musllinux(self, monkeypatch):
        """Wheel filename with musllinux tag should detect MUSL."""
        monkeypatch.delenv("AUDITWHEEL_PLAT", raising=False)
        wheel = Path("pkg-1.0-cp38-cp38-musllinux_1_1_x86_64.whl")
        libc, musl_policy = _detect_libc_and_musl_policy(wheel)
        assert libc == Libc.MUSL
        assert musl_policy == "musllinux_1_1"

    def test_wheel_filename_manylinux(self, monkeypatch):
        """Wheel filename with manylinux tag should detect GLIBC."""
        monkeypatch.delenv("AUDITWHEEL_PLAT", raising=False)
        wheel = Path("pkg-1.0-cp38-cp38-manylinux_2_17_x86_64.whl")
        libc, musl_policy = _detect_libc_and_musl_policy(wheel)
        assert libc == Libc.GLIBC
        assert musl_policy is None

    def test_plain_linux_returns_none(self, monkeypatch):
        """Plain linux_x86_64 wheel with no env var → None (ELF detection)."""
        monkeypatch.delenv("AUDITWHEEL_PLAT", raising=False)
        wheel = Path("pkg-1.0-cp38-cp38-linux_x86_64.whl")
        libc, musl_policy = _detect_libc_and_musl_policy(wheel)
        assert libc is None
        assert musl_policy is None

    def test_auditwheel_plat_takes_priority(self, monkeypatch):
        """AUDITWHEEL_PLAT should override the wheel filename."""
        monkeypatch.setenv("AUDITWHEEL_PLAT", "musllinux_1_2_x86_64")
        wheel = Path("pkg-1.0-cp38-cp38-manylinux_2_17_x86_64.whl")
        libc, musl_policy = _detect_libc_and_musl_policy(wheel)
        assert libc == Libc.MUSL
        assert musl_policy == "musllinux_1_2"


class TestPatchLibcDetection:
    """Verify the libc detection monkeypatch works correctly."""

    def setup_method(self):
        from repairwheel._vendor.auditwheel.policy import WheelPolicies

        self._orig_detect = Libc.detect
        self._orig_wp_init = WheelPolicies.__init__

    def teardown_method(self):
        from repairwheel._vendor.auditwheel.policy import WheelPolicies

        Libc.detect = self._orig_detect
        WheelPolicies.__init__ = self._orig_wp_init

    def test_detect_returns_musl_after_patch(self):
        """After patching, Libc.detect() must return MUSL."""
        monkeypatch.patch_libc_detection(libc=Libc.MUSL, musl_policy=None)
        assert Libc.detect() == Libc.MUSL

    def test_detect_returns_glibc_after_patch(self):
        """After patching with GLIBC, Libc.detect() must return GLIBC."""
        monkeypatch.patch_libc_detection(libc=Libc.GLIBC, musl_policy=None)
        assert Libc.detect() == Libc.GLIBC

    def test_none_defaults_to_musl(self):
        """Patching with libc=None must default detect() to MUSL."""
        monkeypatch.patch_libc_detection(libc=None, musl_policy=None)
        assert Libc.detect() == Libc.MUSL

    def test_wheel_policies_gets_musl_policy(self):
        """After patching with a musl_policy, WheelPolicies should use it."""
        from repairwheel._vendor.auditwheel.architecture import Architecture
        from repairwheel._vendor.auditwheel.policy import WheelPolicies

        monkeypatch.patch_libc_detection(libc=Libc.MUSL, musl_policy="musllinux_1_2")
        policies = WheelPolicies(libc=Libc.MUSL, arch=Architecture("x86_64"))
        # The policy should be musllinux_1_2, not whatever the host has
        assert policies._musl_policy == "musllinux_1_2"


class TestGetWheelPlatforms:
    """Verify get_wheel_platforms recognizes musllinux tags."""

    def test_musllinux_wheel(self, tmp_path):
        """A wheel with a musllinux tag should be recognized as linux."""
        from repairwheel.repair import get_wheel_platforms

        # Create a minimal wheel file with a musllinux tag
        import hashlib
        import zipfile
        from base64 import urlsafe_b64encode

        tag = "cp38-cp38-musllinux_1_2_x86_64"
        dist_info = "pkg-1.0.dist-info"
        metadata = "Metadata-Version: 2.1\nName: pkg\nVersion: 1.0\n"
        wheel_info = f"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: {tag}\n"

        files = {
            f"{dist_info}/METADATA": metadata.encode(),
            f"{dist_info}/WHEEL": wheel_info.encode(),
        }
        record_path = f"{dist_info}/RECORD"
        records = []
        for fname, data in sorted(files.items()):
            digest = urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            records.append(f"{fname},sha256={digest},{len(data)}")
        records.append(f"{record_path},,")
        files[record_path] = "\n".join(records).encode()

        wheel_path = tmp_path / f"pkg-1.0-{tag}.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            for fname, data in files.items():
                zf.writestr(fname, data)

        platforms = get_wheel_platforms(wheel_path)
        assert "linux" in platforms


class TestLinuxRepairSignature:
    def test_repair_accepts_no_exclude(self, monkeypatch, tmp_path):
        import repairwheel._vendor.auditwheel.wheel_abi
        from repairwheel._vendor.auditwheel.error import NonPlatformWheelError
        from repairwheel.linux import repair as linux_repair

        monkeypatch.setattr(linux_repair, "get_machine_from_wheel", lambda w: "x86_64")
        monkeypatch.setattr(linux_repair.monkeypatch, "patch_load_ld_paths", lambda p, s: None)
        monkeypatch.setattr(linux_repair, "_detect_libc_and_musl_policy", lambda w: (None, None))
        monkeypatch.setattr(linux_repair.monkeypatch, "patch_libc_detection", lambda libc, musl: None)

        recorded = {}

        def fake_analyze(libc, arch, wheel_file, exclude, **kwargs):
            recorded["exclude"] = exclude
            raise NonPlatformWheelError("x86_64", [])

        monkeypatch.setattr(repairwheel._vendor.auditwheel.wheel_abi, "analyze_wheel_abi", fake_analyze)

        fake_wheel = tmp_path / "pkg-1.0-cp38-cp38-linux_x86_64.whl"
        # Calling without exclude
        linux_repair.repair(fake_wheel, tmp_path / "out", [], True)
        assert recorded["exclude"] == frozenset()

        # Calling with exclude=None
        linux_repair.repair(fake_wheel, tmp_path / "out", [], True, exclude=None)
        assert recorded["exclude"] == frozenset()

        # Calling with exclude list
        linux_repair.repair(fake_wheel, tmp_path / "out", [], True, exclude=["foo.so"])
        assert recorded["exclude"] == frozenset(["foo.so"])


class TestElfFileAndPatcher:
    """Unit tests for ElfFile, RepairWheelElfPatcher, and fileutil helpers."""

    def test_fileutil_fmove_and_fzero_edge_cases(self, tmp_path: Path):
        from repairwheel.fileutil import fmove, fzero

        path = tmp_path / "data.bin"
        path.write_bytes(b"0123456789abcdef")

        with open(path, "r+b") as fh:
            # No-op cases
            fzero(fh, 4, 0)
            fzero(fh, 4, -5)
            fmove(fh, 2, 2, 8)
            fmove(fh, 0, 4, 0)
            fh.seek(0)
            assert fh.read() == b"0123456789abcdef"

            # Moving past EOF raises EOFError
            with pytest.raises(EOFError):
                fmove(fh, 0, 10, 10)
            with pytest.raises(EOFError):
                fmove(fh, 12, 10, 10)

    def test_patcher_handles_readonly_binary(self, orig_linux_x86_64_wheel, tmp_path: Path):
        import shutil
        import stat
        from repairwheel.linux.patcher import RepairWheelElfPatcher

        so_src = orig_linux_x86_64_wheel.lib_dir / "libtestdep.so"
        so_copy = tmp_path / "libtestdep.so"
        shutil.copyfile(so_src, so_copy)
        so_copy.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

        patcher = RepairWheelElfPatcher()
        assert patcher.get_rpath(so_copy) == ""
        patcher.set_soname(so_copy, "libtestdep-patched.so")
        patcher.set_rpath(so_copy, "$ORIGIN/.libs")
        assert patcher.get_rpath(so_copy) == "$ORIGIN/.libs"
        # Permission bits should be restored after patching
        assert (so_copy.stat().st_mode & 0o777) == 0o444

    def test_elffile_remove_versioned_needed(self, orig_linux_x86_64_wheel, tmp_path: Path):
        from repairwheel.linux.elffile import (
            DT_NEEDED,
            DT_VERNEED,
            DT_VERNEEDNUM,
            ElfFile,
            VerneedEntry,
            get_strtab_entry,
            sizeof,
        )

        so_src = orig_linux_x86_64_wheel.lib_dir / "libtestdep.so"
        so_copy = tmp_path / "libtestdep_verneed.so"
        # Repurpose the 14-byte '.debug_aranges' section name in .shstrtab as '.gnu.version_r'
        so_bytes = so_src.read_bytes().replace(b".debug_aranges", b".gnu.version_r", 1)
        so_copy.write_bytes(so_bytes)

        # Populate the .gnu.version_r section and two versioned DT_NEEDED dependencies
        # into ElfFile to exercise partial and complete removal of versioned dependencies.
        with open(so_copy, "r+b") as fh:
            ef = ElfFile(fh)
            verneed_shdr = ef.get_shdr(b".gnu.version_r")
            verneed_shdr.sh_type = 0x6FFFFFFE  # SHT_GNU_verneed
            verneed_shdr.sh_link = ef.shdr_names.index(b".dynstr")
            verneed_shdr.sh_addralign = ef._class.alignment
            ef.dyn.insert(0, ef._class.Dyn(d_tag=DT_NEEDED, d_ptr_or_val=0))
            ef.verneed_entries = [
                VerneedEntry(
                    verneed=ef._class.Verneed(
                        vn_version=1,
                        vn_cnt=1,
                        vn_file=0,
                        vn_aux=sizeof(ef._class.Verneed),
                        vn_next=0,
                    ),
                    vernaux=[
                        ef._class.Vernaux(
                            vna_hash=0x1234,
                            vna_flags=0,
                            vna_other=2,
                            vna_name=0,
                            vna_next=0,
                        )
                    ],
                    verneed_name=b"libfoo.so.1",
                    vernaux_names=[b"FOO_1.0"],
                ),
                VerneedEntry(
                    verneed=ef._class.Verneed(
                        vn_version=1,
                        vn_cnt=1,
                        vn_file=0,
                        vn_aux=sizeof(ef._class.Verneed),
                        vn_next=0,
                    ),
                    vernaux=[
                        ef._class.Vernaux(
                            vna_hash=0x5678,
                            vna_flags=0,
                            vna_other=3,
                            vna_name=0,
                            vna_next=0,
                        )
                    ],
                    verneed_name=b"libbar.so.1",
                    vernaux_names=[b"BAR_1.0"],
                ),
            ]
            ef.rewrite(needed_replacements={b"": b"libfoo.so.1"})

        with open(so_copy, "r+b") as fh:
            ef = ElfFile(fh)
            assert [ve.verneed_name for ve in ef.verneed_entries] == [b"libfoo.so.1", b"libbar.so.1"]

            # Partial removal: remove libfoo.so.1, keeping libbar.so.1
            ef.rewrite(needed_removals={b"libfoo.so.1"})
            assert [ve.verneed_name for ve in ef.verneed_entries] == [b"libbar.so.1"]
            needed = [get_strtab_entry(ef.dynstr, d.d_ptr_or_val) for d in ef.dyn if d.d_tag == DT_NEEDED]
            assert b"libfoo.so.1" not in needed

            # Complete removal of remaining versioned dependency: remove libbar.so.1
            ef.rewrite(needed_removals={b"libbar.so.1"})
            assert ef.verneed_entries == []
            dyn_tags = {d.d_tag for d in ef.dyn}
            assert DT_VERNEED not in dyn_tags
            assert DT_VERNEEDNUM not in dyn_tags

            # Subsequent rewrite should still succeed cleanly and overwrite last PT_LOAD
            ef.rewrite(new_rpath=b"$ORIGIN")
            assert ef.rpath == b"$ORIGIN"

    def test_elffile_remove_versioned_needed_end_to_end(self, tmp_path: Path):
        import shutil
        import subprocess
        from repairwheel.linux.elffile import DT_NEEDED, DT_VERNEED, DT_VERNEEDNUM, DT_VERSYM, ElfFile, get_strtab_entry

        cc = shutil.which("cc") or shutil.which("gcc")
        if not cc:
            pytest.skip("C compiler required for end-to-end versioned DT_NEEDED test")

        # Build libfoo.so.1 with versioned symbol foo@@FOO_1.0
        (tmp_path / "foo.c").write_text("int foo(void) { return 1; }\n")
        (tmp_path / "foo.map").write_text("FOO_1.0 { global: foo; local: *; };\n")
        libfoo = tmp_path / "libfoo.so.1"
        subprocess.check_call(
            [
                cc,
                "-shared",
                "-fPIC",
                "-Wl,-soname,libfoo.so.1",
                f"-Wl,--version-script,{tmp_path / 'foo.map'}",
                "-o",
                str(libfoo),
                str(tmp_path / "foo.c"),
            ]
        )
        (tmp_path / "libfoo.so").symlink_to(libfoo)

        # Build libbar.so.1 with versioned symbol bar@@BAR_1.0
        (tmp_path / "bar.c").write_text("int bar(void) { return 2; }\n")
        (tmp_path / "bar.map").write_text("BAR_1.0 { global: bar; local: *; };\n")
        libbar = tmp_path / "libbar.so.1"
        subprocess.check_call(
            [
                cc,
                "-shared",
                "-fPIC",
                "-Wl,-soname,libbar.so.1",
                f"-Wl,--version-script,{tmp_path / 'bar.map'}",
                "-o",
                str(libbar),
                str(tmp_path / "bar.c"),
            ]
        )
        (tmp_path / "libbar.so").symlink_to(libbar)

        # Build libm2.so with -nostdlib so .gnu.version_r contains only libfoo.so.1 and libbar.so.1
        (tmp_path / "m2.c").write_text(
            "extern int foo(void); extern int bar(void); int call(void) { return foo() * 10 + bar(); }\n"
        )
        libm2 = tmp_path / "libm2.so"
        subprocess.check_call(
            [
                cc,
                "-shared",
                "-fPIC",
                "-nostdlib",
                "-o",
                str(libm2),
                str(tmp_path / "m2.c"),
                f"-L{tmp_path}",
                "-Wl,--no-as-needed",
                "-lfoo",
                "-lbar",
                f"-Wl,-rpath,{tmp_path}",
            ]
        )

        # Identify which of libfoo.so.1 / libbar.so.1 has the highest vna_other index in .gnu.version_r
        with open(libm2, "r+b") as fh:
            ef = ElfFile(fh)
            overall_max_idx = max(vna.vna_other for ve in ef.verneed_entries for vna in ve.vernaux)
            verneed_by_max_idx = sorted(
                (max(vna.vna_other for vna in ve.vernaux), ve.verneed_name)
                for ve in ef.verneed_entries
                if ve.verneed_name in (b"libfoo.so.1", b"libbar.so.1")
            )
            assert len(verneed_by_max_idx) == 2
            highest_idx, highest_lib = verneed_by_max_idx[-1]
            _, lower_lib = verneed_by_max_idx[0]
            assert highest_idx == overall_max_idx

            # Remove the highest-index versioned library (which previously caused ld.so to SIGSEGV)
            ef.rewrite(needed_removals={highest_lib})
            needed = [get_strtab_entry(ef.dynstr, d.d_ptr_or_val) for d in ef.dyn if d.d_tag == DT_NEEDED]
            assert highest_lib not in needed
            assert lower_lib in needed

        # Load in a subprocess with the removed library preloaded via RTLD_GLOBAL
        preload_path = tmp_path / highest_lib.decode()
        check_code = (
            "import ctypes; "
            f"ctypes.CDLL({str(preload_path)!r}, ctypes.RTLD_GLOBAL); "
            f"m = ctypes.CDLL({str(libm2)!r}); "
            "assert m.call() == 12"
        )
        res = subprocess.run([sys.executable, "-c", check_code], capture_output=True, text=True)
        assert res.returncode == 0, f"Loading patched ELF failed (rc={res.returncode}): {res.stderr}"

        # Also remove the remaining versioned dependency and verify verneed is completely emptied
        with open(libm2, "r+b") as fh:
            ef = ElfFile(fh)
            ef.rewrite(needed_removals={lower_lib})
            assert ef.verneed_entries == []
            dyn_tags = {d.d_tag for d in ef.dyn}
            assert DT_VERNEED not in dyn_tags
            assert DT_VERNEEDNUM not in dyn_tags
            assert DT_VERSYM not in dyn_tags

        check_code_both = (
            "import ctypes; "
            f"ctypes.CDLL({str(libfoo)!r}, ctypes.RTLD_GLOBAL); "
            f"ctypes.CDLL({str(libbar)!r}, ctypes.RTLD_GLOBAL); "
            f"m = ctypes.CDLL({str(libm2)!r}); "
            "assert m.call() == 12"
        )
        res2 = subprocess.run([sys.executable, "-c", check_code_both], capture_output=True, text=True)
        assert res2.returncode == 0, f"Loading patched ELF after second removal failed (rc={res2.returncode}): {res2.stderr}"

    def test_strip_patched_elf_shared_lib_and_executables(self, tmp_path: Path, strip_tool: str):
        import shutil
        import subprocess
        from repairwheel.linux.elffile import ElfFile

        cc = shutil.which("cc") or shutil.which("gcc")
        strip = strip_tool
        if not cc:
            pytest.skip("cc required for ELF strip test")

        # Include enough symbols/debug info so non-alloc sections exceed a 4KB page
        funcs = "\n".join(f"int helper_symbol_{i}(int x) {{ return x + {i}; }}" for i in range(150))
        (tmp_path / "foo.c").write_text(funcs + "\nint foo(void) { return 42; }\n")
        (tmp_path / "main.c").write_text(
            "#include <stdio.h>\n"
            + funcs
            + '\nint foo(void);\nint main(void) { printf("%d\\n", foo()); return foo() == 42 ? 0 : 1; }\n'
        )

        libfoo = tmp_path / "libfoo.so"
        subprocess.check_call([cc, "-shared", "-fPIC", "-g", str(tmp_path / "foo.c"), "-o", str(libfoo)])

        with open(libfoo, "r+b") as fh:
            ef = ElfFile(fh)
            ef.rewrite(new_soname=b"libfoo.so", new_rpath=b"$ORIGIN")

        strip_lib = subprocess.run([strip, str(libfoo)], capture_output=True, text=True, check=True)
        assert strip_lib.stderr == ""
        load_res = subprocess.run(
            [sys.executable, "-c", f"import ctypes; lib = ctypes.CDLL({str(libfoo)!r}); assert lib.foo() == 42"],
            capture_output=True,
            text=True,
        )
        assert load_res.returncode == 0, f"Stripped libfoo.so failed to load (rc={load_res.returncode}): {load_res.stderr}"

        for label, link_flags in [("pie", ["-g"]), ("nopie", ["-no-pie", "-g"])]:
            exe_base = tmp_path / f"main_{label}"
            subprocess.check_call([cc, *link_flags, str(tmp_path / "main.c"), f"-L{tmp_path}", "-lfoo", "-o", str(exe_base)])

            # Test multiple rewrites followed by various strip modes
            for strip_args in [[], ["-s"], ["--strip-debug"], ["--strip-unneeded"]]:
                exe = tmp_path / f"main_{label}_{'_'.join(strip_args) or 'default'}"
                shutil.copy(exe_base, exe)
                with open(exe, "r+b") as fh:
                    ef = ElfFile(fh)
                    ef.rewrite(new_soname=b"long_placeholder_soname_value")
                    ef.rewrite(new_rpath=b"$ORIGIN")
                    ef.rewrite(new_soname=b"short")
                strip_res = subprocess.run([strip, *strip_args, str(exe)], capture_output=True, text=True, check=True)
                assert strip_res.stderr == ""
                run_res = subprocess.run([str(exe)], capture_output=True, text=True)
                assert run_res.returncode == 0 and run_res.stdout.strip() == "42"

            # Test repeated (rewrite -> strip) cycles to ensure no empty PT_LOAD segment is left behind
            exe_cycle = tmp_path / f"main_{label}_cycle"
            shutil.copy(exe_base, exe_cycle)
            expected_phnum = None
            expected_load_count = None
            for i in range(3):
                with open(exe_cycle, "r+b") as fh:
                    ef = ElfFile(fh)
                    ef.rewrite(new_rpath=f"$ORIGIN:{i}".encode())
                    cur_phnum = len(ef.phdrs)
                    cur_load_count = sum(1 for p in ef.phdrs if p.p_type == 1)  # PT_LOAD
                if expected_phnum is None:
                    expected_phnum = cur_phnum
                    expected_load_count = cur_load_count
                else:
                    assert cur_phnum == expected_phnum
                    assert cur_load_count == expected_load_count

                # Second rewrite with same args must be byte-identical (post-strip idempotency)
                bytes_after_first_rewrite = exe_cycle.read_bytes()
                with open(exe_cycle, "r+b") as fh:
                    ef = ElfFile(fh)
                    ef.rewrite(new_rpath=f"$ORIGIN:{i}".encode())
                assert exe_cycle.read_bytes() == bytes_after_first_rewrite

                run_pre = subprocess.run([str(exe_cycle)], capture_output=True, text=True)
                assert run_pre.returncode == 0 and run_pre.stdout.strip() == "42"
                strip_cycle = subprocess.run([strip, str(exe_cycle)], capture_output=True, text=True, check=True)
                assert strip_cycle.stderr == ""
                run_post = subprocess.run([str(exe_cycle)], capture_output=True, text=True)
                assert run_post.returncode == 0 and run_post.stdout.strip() == "42"

    def test_strip_patched_elf_unmapped_phdrs_and_old_layout_migration(self, tmp_path: Path, strip_tool: str):
        import copy
        import io
        import shutil
        import subprocess
        from repairwheel.fileutil import round_to_multiple
        from repairwheel.linux.elffile import PT_LOAD, ElfFile, PositionTracker, sizeof

        cc = shutil.which("cc") or shutil.which("gcc")
        strip = strip_tool
        if not cc:
            pytest.skip("cc required for ELF strip test")

        (tmp_path / "foo.c").write_text("int foo(void) { return 42; }\n")
        lib_base = tmp_path / "libfoo_base.so"
        subprocess.check_call([cc, "-shared", "-fPIC", "-g", str(tmp_path / "foo.c"), "-o", str(lib_base)])

        # 1. Trailer PT_LOAD containing relocated .dynstr/.dynamic while e_phoff is moved to unmapped EOF
        lib_unmapped_phdrs = tmp_path / "libfoo_unmapped_phdrs.so"
        shutil.copy(lib_base, lib_unmapped_phdrs)
        with open(lib_unmapped_phdrs, "r+b") as fh:
            ef = ElfFile(fh)
            ef.rewrite(new_rpath=b"$ORIGIN")
            phdr_count_after_first = len(ef.phdrs)
            load_count_after_first = sum(1 for p in ef.phdrs if p.p_type == PT_LOAD)

            # Copy PHDR table to 8-aligned unmapped space at EOF and point e_phoff there
            phdr_bytes_len = len(ef.phdrs) * sizeof(ef._class.Phdr)
            fh.seek(ef.ehdr.e_phoff)
            raw_phdrs = fh.read(phdr_bytes_len)
            fh.seek(0, io.SEEK_END)
            eof_aligned = round_to_multiple(fh.tell(), ef._class.alignment)
            fh.seek(eof_aligned)
            fh.write(raw_phdrs)
            hdr = copy.deepcopy(ef.ehdr)
            hdr.e_phoff = eof_aligned
            fh.seek(0)
            hdr.to_fileobj(fh)

        # Re-patch, strip, and verify phnum/PT_LOAD count remain constant and library loads
        with open(lib_unmapped_phdrs, "r+b") as fh:
            ef = ElfFile(fh)
            ef.rewrite(new_rpath=b"$ORIGIN/lib")
            assert len(ef.phdrs) == phdr_count_after_first
            assert sum(1 for p in ef.phdrs if p.p_type == PT_LOAD) == load_count_after_first

        strip_res = subprocess.run([strip, str(lib_unmapped_phdrs)], capture_output=True, text=True, check=True)
        assert strip_res.stderr == ""
        load_res = subprocess.run(
            [sys.executable, "-c", f"import ctypes; lib = ctypes.CDLL({str(lib_unmapped_phdrs)!r}); assert lib.foo() == 42"],
            capture_output=True,
            text=True,
        )
        assert load_res.returncode == 0, f"Stripped lib failed to load (rc={load_res.returncode}): {load_res.stderr}"

        # Post-strip re-patching is byte-identical on second pass
        with open(lib_unmapped_phdrs, "r+b") as fh:
            ef = ElfFile(fh)
            ef.rewrite(new_rpath=b"$ORIGIN/lib2")
        bytes_pass1 = lib_unmapped_phdrs.read_bytes()
        with open(lib_unmapped_phdrs, "r+b") as fh:
            ef = ElfFile(fh)
            ef.rewrite(new_rpath=b"$ORIGIN/lib2")
        assert lib_unmapped_phdrs.read_bytes() == bytes_pass1

        # 2. Migration from old layout (PHDRs at the end of the trailer PT_LOAD segment)
        lib_old_layout = tmp_path / "libfoo_old_layout.so"
        shutil.copy(lib_base, lib_old_layout)
        orig_write_new_trailer = ElfFile._write_new_trailer

        def old_layout_trailer(
            self,
            buf,
            file_offset,
            vm_offset,
            new_soname=None,
            new_rpath=None,
            needed_replacements=None,
            needed_removals=None,
            add_new_load=False,
        ):
            # Reproduce old layout by writing without initial PHDR reservation and without back_to_start
            orig_back_to_start = PositionTracker.back_to_start
            call_count = 0
            orig_write_phdrs = ElfFile._write_phdrs

            def skip_first_write_phdrs(self_ef, b, pos, dyn_pos, add_load):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return None
                return orig_write_phdrs(self_ef, b, pos, dyn_pos, add_load)

            PositionTracker.back_to_start = lambda self_pos: None
            ElfFile._write_phdrs = skip_first_write_phdrs
            try:
                return orig_write_new_trailer(
                    self,
                    buf,
                    file_offset,
                    vm_offset,
                    new_soname,
                    new_rpath,
                    needed_replacements,
                    needed_removals,
                    add_new_load,
                )
            finally:
                PositionTracker.back_to_start = orig_back_to_start
                ElfFile._write_phdrs = orig_write_phdrs

        with open(lib_old_layout, "r+b") as fh:
            ef = ElfFile(fh)
            ElfFile._write_new_trailer = old_layout_trailer
            try:
                ef.rewrite(new_rpath=b"$ORIGIN")
            finally:
                ElfFile._write_new_trailer = orig_write_new_trailer

        # Re-patch old-layout binary with current code, strip, and verify it loads cleanly
        with open(lib_old_layout, "r+b") as fh:
            ef = ElfFile(fh)
            ef.rewrite(new_rpath=b"$ORIGIN/migrated")

        strip_migrated = subprocess.run([strip, str(lib_old_layout)], capture_output=True, text=True, check=True)
        assert strip_migrated.stderr == ""
        load_migrated = subprocess.run(
            [sys.executable, "-c", f"import ctypes; lib = ctypes.CDLL({str(lib_old_layout)!r}); assert lib.foo() == 42"],
            capture_output=True,
            text=True,
        )
        assert load_migrated.returncode == 0, f"Migrated stripped lib failed to load (rc={load_migrated.returncode})"
