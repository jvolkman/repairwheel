import os
import re
import pathlib
import subprocess
import sys
import tempfile
import zipfile


test_root = pathlib.Path(__file__).parent.resolve()
lib_dir = test_root / "testwheel" / "lib"

linux_wheel = test_root / "testwheel" / "testwheel-0.0.1-cp36-abi3-linux_x86_64.whl"
macos_wheel = test_root / "testwheel" / "testwheel-0.0.1-cp36-abi3-macosx_11_0_arm64.whl"
windows_wheel = test_root / "testwheel" / "testwheel-0.0.1-cp36-abi3-win_amd64.whl"


def check_call(args: list):
    return subprocess.check_call(args, env=os.environ)


def patch(wheel: pathlib.Path, out_dir: pathlib.Path) -> pathlib.Path:
    before = list(out_dir.glob("*.whl"))
    check_call(
        [
            sys.executable,
            "-m",
            "repairwheel",
            "--lib-dir",
            lib_dir,
            wheel,
            "--output-dir",
            str(tmp),
        ]
    )
    files = list(pathlib.Path(tmp).glob("*.whl"))
    assert len(files) == 1, "Expected one output wheel to be generated"
    return files[0]


@pytest.fixture
def 



@p
def 



def test_patched_testwheel_runs():
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
