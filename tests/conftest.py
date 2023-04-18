import tempfile
from pathlib import Path

import pytest

from .util import get_patched_wheel, TestWheel


@pytest.fixture(scope="session")
def testwheel_root() -> Path:
    return Path(__file__).parent / "testwheel"


@pytest.fixture(scope="session")
def patched_wheel_area() -> Path:
    with tempfile.TemporaryDirectory(prefix="testwheel") as temp_dir:
        yield (Path(temp_dir))


@pytest.fixture(scope="session")
def orig_py3_none_any_wheel(testwheel_root: Path) -> TestWheel:
    tag = "py3-none-any"
    return TestWheel(
        tag,
        testwheel_root / tag / f"testwheel-0.0.1-{tag}.whl",
    )


@pytest.fixture(scope="session")
def patched_py3_none_any_wheel(orig_py3_none_any_wheel: TestWheel, patched_wheel_area: Path) -> Path:
    return get_patched_wheel(orig_py3_none_any_wheel, patched_wheel_area)


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
        "patched_py3_none_any_wheel",
        "patched_linux_x86_64_wheel",
        "patched_macos_x86_64_wheel",
        "patched_macos_arm64_wheel",
        "patched_windows_x86_64_wheel",
    ]
)
def patched_wheel(request) -> Path:
    return request.getfixturevalue(request.param)
