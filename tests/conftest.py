from dataclasses import dataclass
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


@dataclass
class TestWheel:
    tag: str
    wheel: Path
    lib_dir: Path


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


def get_patched_wheel(testwheel: TestWheel, patched_wheel_area: Path) -> Path:
    out_dir = patched_wheel_area / testwheel.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    patch_wheel(testwheel.wheel, testwheel.lib_dir, out_dir)
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
def orig_linux_x86_64_wheel(testwheel_root: Path) -> TestWheel:
    tag = "cp36-abi3-linux_x86_64"
    return TestWheel(
        tag,
        testwheel_root / tag / f"testwheel-0.0.1-{tag}.whl",
        testwheel_root / tag / "lib",
    )


@pytest.fixture(scope="session")
def patched_linux_x86_64_wheel(orig_linux_x86_64_wheel: TestWheel, patched_wheel_area: Path) -> Path:
    return get_patched_wheel(orig_linux_x86_64_wheel, patched_wheel_area)


@pytest.fixture(scope="session")
def orig_macos_x86_64_wheel(testwheel_root: Path) -> TestWheel:
    tag = "cp36-abi3-macosx_10_11_x86_64"
    return TestWheel(
        tag,
        testwheel_root / tag / f"testwheel-0.0.1-{tag}.whl",
        testwheel_root / tag / "lib",
    )


@pytest.fixture(scope="session")
def patched_macos_x86_64_wheel(orig_macos_x86_64_wheel: Path, patched_wheel_area: Path) -> Path:
    return get_patched_wheel(orig_macos_x86_64_wheel, patched_wheel_area)


@pytest.fixture(scope="session")
def orig_macos_arm64_wheel(testwheel_root: Path) -> TestWheel:
    tag = "cp36-abi3-macosx_10_11_arm64"
    return TestWheel(
        tag,
        testwheel_root / tag / f"testwheel-0.0.1-{tag}.whl",
        testwheel_root / tag / "lib",
    )


@pytest.fixture(scope="session")
def patched_macos_arm64_wheel(orig_macos_arm64_wheel: Path, patched_wheel_area: Path) -> Path:
    return get_patched_wheel(orig_macos_arm64_wheel, patched_wheel_area)


@pytest.fixture(scope="session")
def orig_windows_x86_64_wheel(testwheel_root: Path) -> TestWheel:
    tag = "cp36-abi3-win_amd64"
    return TestWheel(
        tag,
        testwheel_root / tag / f"testwheel-0.0.1-{tag}.whl",
        testwheel_root / tag / "lib",
    )


@pytest.fixture(scope="session")
def patched_windows_x86_64_wheel(orig_windows_x86_64_wheel: TestWheel, patched_wheel_area: Path) -> Path:
    return get_patched_wheel(orig_windows_x86_64_wheel, patched_wheel_area)


@pytest.fixture(
    params=[
        "patched_linux_x86_64_wheel",
        "patched_macos_x86_64_wheel",
        "patched_macos_arm64_wheel",
        "patched_windows_x86_64_wheel",
    ]
)
def patched_wheel(request) -> Path:
    return request.getfixturevalue(request.param)
