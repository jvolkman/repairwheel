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
    return re.match(r'^[^-]+-[0-9a-f]{32}\.dll$', filename.lower()) is not None


def test_basic():
    """Basic repair for the iknowpy package"""

    test_dir = pathlib.Path(__file__).parent

    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        check_call([
            sys.executable, 
            '-m', 
            'repairwheel',
            '--lib-dir',
            test_dir / 'iknowpy',
            test_dir / 'iknowpy'/ 'iknowpy-1.5.0-cp310-cp310-win_amd64.whl',
            '--output-dir',
            str(tmp),
        ])
        with zipfile.ZipFile(tmp / 'iknowpy-1.5.0-cp310-cp310-win_amd64.whl') as wheel:
            for path in zipfile.Path(wheel, 'iknowpy.libs/').iterdir():
                if path.name in ('.load-order-iknowpy-1.5.0', 'concrt140.dll', 'msvcp140.dll'):
                    continue
                assert is_mangled(path.name), f'{path.name} is mangled'
