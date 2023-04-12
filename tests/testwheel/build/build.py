#!/usr/bin/env python3

import argparse
import base64
import hashlib
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


SCRIPT_DIR = Path(__file__).parent.resolve()
WHEEL_NAME = "testwheel"
WHEEL_VERSION = "0.0.1"

METADATA = f"""\
Metadata-Version: 2.1
Name: {WHEEL_NAME}
Version: {WHEEL_VERSION}
"""


@dataclass
class BuildInfo:
    target: str
    tag: str
    dep_cflags: List[str]
    dep_name: str
    ext_cflags: List[str]
    ext_name: str
    python_url: str


LINUX_X86_64_BUILD = BuildInfo(
    target="x86_64-linux",
    tag="cp36-abi3-linux_x86_64",
    dep_cflags=["-shared", "-Wl,-soname,libtestdep.so"],
    dep_name="libtestdep.so",
    ext_cflags=["-shared", "-I{pydir}/python/include/python3.10", "-I{testdep}", "-L{lib}", "-ltestdep"],
    ext_name=f"{WHEEL_NAME}.abi3.so",
    python_url="https://github.com/indygreg/python-build-standalone/releases/download/20230116/cpython-3.10.9+20230116-x86_64-unknown-linux-gnu-install_only.tar.gz",
)


MACOS_ARM64_BUILD = BuildInfo(
    target="aarch64-macos",
    tag="cp36-abi3-macosx_10_11_arm64",
    dep_cflags=["-shared", "-install_name", "libtestdep.dylib", "-Wl,-headerpad_max_install_names"],
    dep_name="libtestdep.dylib",
    ext_cflags=[
        "-shared",
        "-Wl,-undefined,dynamic_lookup",
        "-Wl,-headerpad_max_install_names",
        "-I{pydir}/python/include/python3.10",
        "-I{testdep}",
        "-L{lib}",
        "-ltestdep",
    ],
    ext_name=f"{WHEEL_NAME}.abi3.so",
    python_url="https://github.com/indygreg/python-build-standalone/releases/download/20230116/cpython-3.10.9+20230116-aarch64-apple-darwin-install_only.tar.gz",
)


MACOS_X86_64_BUILD = BuildInfo(
    target="x86_64-macos",
    tag="cp36-abi3-macosx_10_11_x86_64",
    dep_cflags=["-shared", "-install_name", "libtestdep.dylib", "-Wl,-headerpad_max_install_names"],
    dep_name="libtestdep.dylib",
    ext_cflags=[
        "-shared",
        "-Wl,-undefined,dynamic_lookup",
        "-Wl,-headerpad_max_install_names",
        "-I{pydir}/python/include/python3.10",
        "-I{testdep}",
        "-L{lib}",
        "-ltestdep",
    ],
    ext_name=f"{WHEEL_NAME}.abi3.so",
    python_url="https://github.com/indygreg/python-build-standalone/releases/download/20230116/cpython-3.10.9+20230116-x86_64-apple-darwin-install_only.tar.gz",
)


WINDOWS_X86_64_BUILD = BuildInfo(
    target="x86_64-windows",
    tag="cp36-abi3-win_amd64",
    dep_cflags=["-DMS_WIN64", "-shared"],
    dep_name="testdep.dll",
    ext_cflags=[
        "-DMS_WIN64",
        "-shared",
        "-I{pydir}/python/include",
        "-I{testdep}",
        "-L{pydir}/python/libs",
        "-L{lib}",
        "-lpython3",
        "-ltestdep",
    ],
    ext_name=f"{WHEEL_NAME}.pyd",
    python_url="https://github.com/indygreg/python-build-standalone/releases/download/20230116/cpython-3.10.9+20230116-x86_64-pc-windows-msvc-shared-install_only.tar.gz",
)


def fetch_python(build_info: BuildInfo, build_dir: Path) -> Path:
    urllib.request.urlretrieve(build_info.python_url, str(build_dir / "python.tgz"))
    python_dir = build_dir / "python"
    with tarfile.open(build_dir / "python.tgz") as tf:
        tf.extractall(python_dir)

    return python_dir


def build_testdep(build_info: BuildInfo, build_dir: Path) -> Path:
    print(f"Building {build_info.dep_name}")
    out_file = build_dir / "testdep" / build_info.dep_name
    out_file.parent.mkdir(parents=True, exist_ok=True)
    args = ["zig", "cc", "-target", build_info.target, "-o", str(out_file), "testdep.c"]
    args += build_info.dep_cflags
    subprocess.check_call(args, cwd=SCRIPT_DIR / "testdep")

    return out_file


def build_ext(build_info: BuildInfo, build_dir: Path, python_dir: Path, lib_dir: Path) -> Path:
    print(f"Building {build_info.ext_name}")
    fmt = {
        "pydir": str(python_dir),
        "lib": str(lib_dir),
        "testdep": str(SCRIPT_DIR / "testdep"),
    }

    out = build_dir / "ext"
    out.mkdir(parents=True, exist_ok=True)
    out_file = out / build_info.ext_name
    args = ["zig", "cc", "-target", build_info.target, "-o", str(out_file), "testwheel.c"]
    args += [flag.format(**fmt) for flag in build_info.ext_cflags]
    subprocess.check_call(args, cwd=SCRIPT_DIR)

    return out_file


def build_wheel_manifest(build_info: BuildInfo) -> str:
    lines = [
        "Wheel-Version: 1.0",
        "Generator: build.py",
        "Root-Is-Purelib: false",
        f"Tag: {build_info.tag}",
    ]
    return "\n".join(lines) + "\n"


def build_record(files: Dict[str, bytes], record_file: str) -> str:
    records = []
    for fname in sorted(files):
        data = files[fname]
        sha256_hash = hashlib.sha256(data).digest()
        hash_str = base64.urlsafe_b64encode(sha256_hash)
        records.append(f"{fname},sha256={hash_str},{len(data)}")
    records.append(f"{record_file},,")
    return "\n".join(records) + "\n"


def build_wheel(build_info: BuildInfo, ext_file: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    wheel_file = out_dir / f"{WHEEL_NAME}-{WHEEL_VERSION}-{build_info.tag}.whl"
    print(f"Building {wheel_file}")

    with open(ext_file, "rb") as ext_file:
        ext_bytes = ext_file.read()

    record_file = f"{WHEEL_NAME}-{WHEEL_VERSION}.dist-info/RECORD"
    files = {
        f"repairwheel_test/{build_info.ext_name}": ext_bytes,
        f"{WHEEL_NAME}-{WHEEL_VERSION}.dist-info/top_level.txt": b"test\n",
        f"{WHEEL_NAME}-{WHEEL_VERSION}.dist-info/METADATA": METADATA.encode("utf-8"),
        f"{WHEEL_NAME}-{WHEEL_VERSION}.dist-info/WHEEL": build_wheel_manifest(build_info).encode("utf-8"),
    }

    record = build_record(files, record_file)
    files[record_file] = record.encode("utf-8")

    wheel_file = out_dir / f"{WHEEL_NAME}-{WHEEL_VERSION}-{build_info.tag}.whl"
    with zipfile.ZipFile(wheel_file, "w", zipfile.ZIP_DEFLATED) as zip:
        for fname in sorted(files):
            data = files[fname]
            zip.writestr(fname, data)


def build(build_info: BuildInfo, build_dir: Path, out_dir: Path):
    build_dir = build_dir / f"_build_{build_info.target}"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    testdep_file = build_testdep(build_info, build_dir)
    out_dir = out_dir / build_info.tag
    out_lib_dir = out_dir / "lib"
    out_lib_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(testdep_file, out_lib_dir / testdep_file.name)

    python_dir = fetch_python(build_info, build_dir)
    ext_file = build_ext(build_info, build_dir, python_dir, testdep_file.parent)

    build_wheel(build_info, ext_file, out_dir)


if __name__ == "__main__":
    build_choices = {
        "linux_x86_64": [LINUX_X86_64_BUILD],
        "macos_x86_64": [MACOS_X86_64_BUILD],
        "macos_arm64": [MACOS_ARM64_BUILD],
        "windows_x86_64": [WINDOWS_X86_64_BUILD],
    }
    all = []
    for v in build_choices.values():
        all.extend(v)
    build_choices["all"] = all

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", choices=list(build_choices), required=True)
    parser.add_argument("--no-cleanup", action="store_true")
    args = parser.parse_args()

    out_dir = args.output.resolve()
    build_dir = Path(tempfile.mkdtemp(prefix="testwheel"))

    print(f"Build temp: {build_dir}")

    build_infos = build_choices[args.target]
    try:
        for info in build_infos:
            build(info, build_dir, out_dir)

    finally:
        if not args.no_cleanup:
            shutil.rmtree(build_dir)
