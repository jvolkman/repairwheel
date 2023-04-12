import platform
import zipfile
from pathlib import Path

import pytest

from .util import check_wheel_installs_and_runs, is_wheel_compatible


def test_wheel_contains_testdep(patched_wheel: Path) -> None:
    with zipfile.ZipFile(patched_wheel, "r") as zf:
        for file in zf.filelist:
            if "testdep" in file.filename.lower():
                break
        else:
            raise AssertionError(f"testdep not found in wheel: {patched_wheel}")


def test_wheel_installs_and_runs(patched_wheel: Path) -> None:
    if not is_wheel_compatible(patched_wheel):
        pytest.skip(f"Wheel not installable on {platform.platform()}: {patched_wheel.name}")
    check_wheel_installs_and_runs(patched_wheel)
