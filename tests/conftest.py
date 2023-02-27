from pathlib import Path
from typing import List
import pytest


@pytest.fixture(scope="session")
def test_root() -> Path:
    return Path(__file__).parent


@pytest.fixture(scope="session")
def win_amd64_whl(test_root: Path) -> Path:
    return test_root / "testwheel" / "testwheel-0.0.1-cp36-win_amd64.whl"


@pytest.fixture(scope="session")
def macos_arm64_whl(test_root: Path) -> Path:
    return test_root / "testwheel" / "testwheel-0.0.1-cp36-macosx_11_0_arm64.whl"


@pytest.fixture(scope="session")
def linux_x86_64_whl(test_root: Path) -> Path:
    return test_root / "testwheel" / "testwheel-0.0.1-cp36-linux_x86_64.whl"


@pytest.fixture(scope="session")
def all_wheels(win_amd64_whl: Path, macos_arm64_whl: Path, linux_x86_64_whl: Path) -> List[Path]:
    return [
        win_amd64_whl,
        macos_arm64_whl,
        linux_x86_64_whl,
    ]
