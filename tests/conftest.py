import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


def patch_wheel(wheel: Path, lib_dir: Path, out_dir: Path) -> None:
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "repairwheel",
            "--lib-dir",
            str(lib_dir),
            str(wheel),
            "--output-dir",
            str(out_dir),
        ],
        env=os.environ,
    )


def get_patched_wheel(platform: str, wheel: Path, testwheel_root: Path, patched_wheel_area: Path) -> Path:
    out_dir = patched_wheel_area / platform
    out_dir.mkdir(parents=True, exist_ok=True)
    lib_dir = testwheel_root / "lib"
    patch_wheel(wheel, lib_dir, out_dir)
    files = list(out_dir.glob("*.whl"))
    assert len(files) == 1, f"Found {len(files)} wheels in {out_dir}"
    return files[0]


@pytest.fixture(scope="session")
def testwheel_root() -> Path:
    return Path(__file__).parent / "testwheel"


@pytest.fixture(scope="session")
def patched_wheel_area() -> Path:
    with tempfile.TemporaryDirectory(prefix="testwheel") as temp_dir:
        yield (Path(temp_dir))


@pytest.fixture(scope="session")
def orig_linux_wheel(testwheel_root: Path) -> Path:
    return testwheel_root / "testwheel-0.0.1-cp36-abi3-linux_x86_64.whl"


@pytest.fixture(scope="session")
def patched_linux_wheel(orig_linux_wheel: Path, testwheel_root: Path, patched_wheel_area: Path) -> Path:
    return get_patched_wheel("linux", orig_linux_wheel, testwheel_root, patched_wheel_area)


@pytest.fixture(scope="session")
def orig_macos_wheel(testwheel_root: Path) -> Path:
    return testwheel_root / "testwheel-0.0.1-cp36-abi3-macosx_11_0_arm64.whl"


@pytest.fixture(scope="session")
def patched_macos_wheel(orig_macos_wheel: Path, testwheel_root: Path, patched_wheel_area: Path) -> Path:
    return get_patched_wheel("macos", orig_macos_wheel, testwheel_root, patched_wheel_area)


@pytest.fixture(scope="session")
def orig_windows_wheel(testwheel_root: Path) -> Path:
    return testwheel_root / "testwheel-0.0.1-cp36-abi3-win_amd64.whl"


@pytest.fixture(scope="session")
def patched_windows_wheel(orig_windows_wheel: Path, testwheel_root: Path, patched_wheel_area: Path) -> Path:
    return get_patched_wheel("windows", orig_windows_wheel, testwheel_root, patched_wheel_area)


@pytest.fixture(params=["patched_linux_wheel", "patched_macos_wheel", "patched_windows_wheel"])
def patched_wheel(request) -> Path:
    return request.getfixturevalue(request.param)
