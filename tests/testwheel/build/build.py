
from dataclasses import dataclass
import enum
import tarfile
from typing import List
from pathlib import Path
import urllib.request


@dataclass
class BuildInfo:
    dep_cflags: List[str]
    dep_name: str
    ext_cflags: List[str]
    ext_name: str
    python_url: str



LINUX_BUILD = BuildInfo(
    target="x86_64-linux",
    dep_cflags=["-shared", "-Wl,-soname,libtestdep.so"],
    dep_name="libtestdep.so",
    ext_cflags=["-shared", "-I{pydir}/python/include", "I{testdep}", "-L{lib}", "-ltestdep"],
    ext_name="testwheel.abi3.so",
    python_url="https://github.com/indygreg/python-build-standalone/releases/download/20230116/cpython-3.10.9+20230116-x86_64-unknown-linux-gnu-install_only.tar.gz",
)


MACOS_BUILD = BuildInfo(
    target="aarch64-macos",
    dep_cflags=["-shared", "-Wl,-install-name,libtestdep.dylib"],
    dep_name="libtestdep.dylib",
    ext_cflags=["-bundle", "-Wl,-undefined,dynamic_lookup", "-I{pydir}/python/include", "I{testdep}", "-L{lib}", "-ltestdep"],
    ext_name="testwheel.abi3.so",
    python_url="https://github.com/indygreg/python-build-standalone/releases/download/20230116/cpython-3.10.9+20230116-aarch64-apple-darwin-install_only.tar.gz"
)


WINDOWS_BUILD = BuildInfo(
    target="x86_64-windows",
    dep_cflags=["-DMS_WIN64", "-shared"],
    dep_name="testdep.dll",
    ext_cflags=["-DMS_WIN64", "-shared", "-I{pydir}/python/include", "-I{testdep}", "-L{pydir}/python/libs", "-L{lib}", "-lpython3", "-ltestdep"],
    ext_name="testwheel.pyd",
    python_url="https://github.com/indygreg/python-build-standalone/releases/download/20230116/cpython-3.10.9+20230116-x86_64-pc-windows-msvc-shared-install_only.tar.gz",
)


def fetch_python(build_info: BuildInfo, build_dir: Path) -> Path:
    urllib.request.urlretrieve(build_info.python_url, str(build_dir / "python.tgz"))
    python_dir = build_dir / 'python'
    with tarfile.open(build_dir / 'python.tgz') as tf:
        tf.extractall(python_dir)

    return python_dir



def build_testdep():
    pass


def build(build_info: BuildInfo):
    pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", choices=["linux", "macos", "windows"], required=True)
    args = parser.parse_args()
    print(args.echo)
    build(LINUX_BUILD)
