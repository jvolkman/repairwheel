import os
import re
import zipfile


def is_mangled(filename: str) -> bool:
    """Return True if filename is a name-mangled DLL name, False otherwise."""
    return re.match(r"^[^-]+-[0-9a-f]{32}\.dll$", filename.lower()) is not None


def test_testwheel(patched_windows_x86_64_wheel):
    """Basic repair for the testwheel package"""
    with zipfile.ZipFile(patched_windows_x86_64_wheel) as wheel:
        for info in wheel.infolist():
            if info.filename.startswith("testwheel.libs/"):
                name = os.path.basename(info.filename)
                if name.startswith("testdep-"):
                    assert is_mangled(name), f"{name} is mangled"
                    break
        else:
            raise AssertionError("did not find testdep dll")
