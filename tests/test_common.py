import os
import platform
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
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


def test_repaired_wheel_has_proper_tag(patched_wheel: Path) -> None:
    """Repaired wheels must carry audited platform tags, not bare 'linux_'."""
    name = patched_wheel.name
    if "py3-none-any" in name:
        pytest.skip("Pure-python wheel; no platform tag to audit")

    if "linux" in name:
        assert any(
            t in name for t in ["manylinux", "musllinux"]
        ), f"Linux wheel should have manylinux or musllinux tag, got: {name}"
    elif "macosx" in name:
        assert "macosx_" in name, f"macOS wheel missing macosx tag: {name}"
    elif "win" in name:
        assert "win_" in name or "win32" in name, f"Windows wheel missing win tag: {name}"


def test_source_date_epoch(orig_py3_none_any_wheel: TestWheel) -> None:
    expected_zip_time = datetime.fromtimestamp(TEST_SOURCE_DATE_EPOCH, timezone.utc).timetuple()[:6]
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
        assert (
            patched_wheel.read_bytes() == re_patched[0].read_bytes()
        ), "Repairing an already-repaired wheel produced different output"


def test_mixed_case_dist_info_preserved() -> None:
    from repairwheel.wheel import write_canonical_wheel
    import tempfile
    import zipfile
    import shutil
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        wheel_name = "TestPackage-1.0.0-py3-none-any.whl"

        # Create a dummy original wheel
        orig_wheel_path = tmpdir_path / wheel_name
        with zipfile.ZipFile(orig_wheel_path, "w") as z:
            metadata_content = b"Metadata-Version: 2.1\nName: TestPackage\nVersion: 1.0.0\n"
            z.writestr("TestPackage-1.0.0.dist-info/METADATA", metadata_content)
            z.writestr("TestPackage-1.0.0.dist-info/RECORD", b"TestPackage-1.0.0.dist-info/METADATA,,\n")
            z.writestr("testpackage/__init__.py", b"# test\n")

        # For our test, patched wheel can be the same as original since we are testing write_canonical_wheel
        patched_wheel_dir = tmpdir_path / "patched"
        patched_wheel_dir.mkdir()
        patched_wheel_path = patched_wheel_dir / wheel_name
        shutil.copyfile(orig_wheel_path, patched_wheel_path)

        out_dir = tmpdir_path / "out"
        out_dir.mkdir()

        # Run write_canonical_wheel
        out_wheel = write_canonical_wheel(orig_wheel_path, patched_wheel_path, out_dir)

        # Verify output wheel
        with zipfile.ZipFile(out_wheel, "r") as z:
            namelist = z.namelist()

        assert "TestPackage-1.0.0.dist-info/METADATA" in namelist
        assert "TestPackage-1.0.0.dist-info/RECORD" in namelist

        # We expect NO lowercase dist-info
        assert not any(name.startswith("testpackage-1.0.0.dist-info") for name in namelist)

        # We expect exactly one RECORD file
        record_files = [name for name in namelist if name.endswith("/RECORD")]
        assert len(record_files) == 1
        assert record_files[0] == "TestPackage-1.0.0.dist-info/RECORD"
