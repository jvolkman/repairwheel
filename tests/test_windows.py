import re
import zipfile


def is_mangled(filename: str) -> bool:
    """Return True if filename is a name-mangled DLL name, False otherwise."""
    return re.match(r"^[^-]+-[0-9a-f]{32}\.dll$", filename.lower()) is not None


def test_testwheel(patched_windows_wheel):
    """Basic repair for the testwheel package"""
    with zipfile.ZipFile(patched_windows_wheel) as wheel:
        for path in zipfile.Path(wheel, "testwheel.libs/").iterdir():
            if path.name.startswith("testdep-"):
                assert is_mangled(path.name), f"{path.name} is mangled"
                break
        else:
            assert False, "did not find testdep dll"
