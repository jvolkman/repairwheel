import os
import re
import pathlib
import subprocess
import sys
import tempfile
import zipfile


def check_call(args: list):
    return subprocess.check_call(args, env=os.environ)


def is_mangled(filename: str) -> bool:
    """Return True if filename is a name-mangled DLL name, False otherwise."""
    return re.match(r"^[^-]+-[0-9a-f]{32}\.dll$", filename.lower()) is not None


def test_testwheel():
    """Basic repair for the testwheel package"""

    test_dir = pathlib.Path(__file__).parent

    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        check_call(
            [
                sys.executable,
                "-m",
                "repairwheel",
                "--lib-dir",
                test_dir / "testwheel" / "lib",
                test_dir / "testwheel" / "testwheel-0.0.1-cp36-abi3-win_amd64.whl",
                "--output-dir",
                str(tmp),
            ]
        )
        with zipfile.ZipFile(tmp / "testwheel-0.0.1-cp36-abi3-win_amd64.whl") as wheel:
            for path in zipfile.Path(wheel, "testwheel.libs/").iterdir():
                if path.name.startswith("testdep-"):
                    assert is_mangled(path.name), f"{path.name} is mangled"
                    break
            else:
                assert False, "did not find testdep dll"
