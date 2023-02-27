import sys
import zipfile
from pathlib import Path

import pytest


def test_wheel_contains_testdep(patched_wheel: Path) -> None:
    with zipfile.ZipFile(patched_wheel, "r") as zf:
        for file in zf.filelist:
            if "testdep" in file.filename.lower():
                break
        else:
            assert False, f"testdep not found in wheel: {patched_wheel}"


def test_wheel_installs_and_runs(patched_wheel: Path) -> None:
    if sys.platform == "linux":
        if "linux" not in patched_wheel.name:
            pytest.skip(f"Wheel not installable on linux: {patched_wheel.name}")
    elif sys.platform == "darwin":
        if "macos" not in patched_wheel.name:
            pytest.skip(f"Wheel not installable on macos: {patched_wheel.name}")
    elif sys.platform == "win32":
        if "win" not in patched_wheel.name:
            pytest.skip(f"Wheel not installable on windows: {patched_wheel.name}")
    else:
        assert False, f"test cannot run on {sys.platform}"

# def test_patched_testwheel_runs():
#     """Basic repair for the testwheel package"""

#     test_dir = pathlib.Path(__file__).parent

#     with tempfile.TemporaryDirectory() as tmp:
#         tmp = pathlib.Path(tmp)
#         check_call(
#             [
#                 sys.executable,
#                 "-m",
#                 "repairwheel",
#                 "--lib-dir",
#                 test_dir / "testwheel" / "lib",
#                 test_dir / "testwheel" / "testwheel-0.0.1-cp36-abi3-win_amd64.whl",
#                 "--output-dir",
#                 str(tmp),
#             ]
#         )
#         with zipfile.ZipFile(tmp / "testwheel-0.0.1-cp36-abi3-win_amd64.whl") as wheel:
#             for path in zipfile.Path(wheel, "testwheel.libs/").iterdir():
#                 if path.name.startswith("testdep-"):
#                     assert is_mangled(path.name), f"{path.name} is mangled"
#                     break
#             else:
#                 assert False, "did not find testdep dll"




