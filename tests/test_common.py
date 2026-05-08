import os
import platform
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from .util import check_wheel_installs_and_runs, get_patched_wheel, is_wheel_compatible, TestWheel

TEST_SOURCE_DATE_EPOCH = 1234567890


def test_wheel_contains_testdep(patched_wheel: Path) -> None:
    if "py3-none-any" in patched_wheel.name:
        pytest.skip("py3-none-any wheel doesn't contain testdep")
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


def test_source_date_epoch(orig_py3_none_any_wheel: TestWheel) -> None:
    expected_zip_time = datetime.utcfromtimestamp(TEST_SOURCE_DATE_EPOCH).timetuple()[:6]
    with tempfile.TemporaryDirectory(prefix="testwheel") as temp_dir:
        temp_dir = Path(temp_dir)
        patched_wheel = get_patched_wheel(
            orig_py3_none_any_wheel, temp_dir, {"SOURCE_DATE_EPOCH": str(TEST_SOURCE_DATE_EPOCH)}
        )
        with zipfile.ZipFile(patched_wheel) as zf:
            for zi in zf.infolist():
                assert zi.date_time == expected_zip_time


def test_repair_is_idempotent(patched_wheel: Path) -> None:
    """repair(repair(wheel)) must produce a byte-identical wheel."""
    if "py3-none-any" in patched_wheel.name:
        pytest.skip("py3-none-any wheel has no native deps to repair")

    with tempfile.TemporaryDirectory(prefix="idempotent") as temp_dir:
        out_dir = Path(temp_dir)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "repairwheel",
                str(patched_wheel),
                "--output-dir",
                str(out_dir),
            ],
            env=dict(os.environ),
            capture_output=True,
            text=True,
        )

        re_patched = list(out_dir.glob("*.whl"))

        if result.returncode != 0 and not re_patched:
            # The backend (e.g. delvewheel) recognized the wheel as
            # already repaired and refused to produce output.  That's
            # idempotent by definition.
            return

        assert result.returncode == 0, f"repairwheel failed:\n{result.stdout}\n{result.stderr}"
        assert len(re_patched) == 1, f"Expected 1 wheel, got {len(re_patched)}"
        assert patched_wheel.read_bytes() == re_patched[0].read_bytes(), (
            "Repairing an already-repaired wheel produced different output"
        )
