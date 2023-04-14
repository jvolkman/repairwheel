import hashlib
import os
import platform
from collections import defaultdict
from pathlib import Path

import pytest

from ..util import check_wheel_installs_and_runs, is_wheel_compatible

BUF_SIZE = 65536
GEN_PATH = os.environ.get("TESTWHEEL_GENERATE_PATH")

if GEN_PATH is None:
    pytest.skip(allow_module_level=True)


def hash(file: Path) -> str:
    md5 = hashlib.md5()
    with open(file, "rb") as f:
        while True:
            data = f.read(BUF_SIZE)
            if not data:
                break
            md5.update(data)
    return md5.hexdigest()


@pytest.mark.parametrize(
    "patched_wheel",
    Path(GEN_PATH).glob("**/*.whl"),
    ids=lambda p: os.path.relpath(str(p), GEN_PATH),
)
def test_check_patched_wheel(patched_wheel: Path) -> None:
    if not is_wheel_compatible(patched_wheel):
        pytest.skip(f"Wheel not installable on {platform.platform()}: {patched_wheel.name}")
    check_wheel_installs_and_runs(patched_wheel)


def test_check_reproducibility() -> None:
    hashes = defaultdict(set)
    wheels = Path(GEN_PATH).glob("**/*.whl")

    for wheel in wheels:
        hashes[wheel.name].add(hash(wheel))

    non_reproducible = []
    for wheel_name, hash_set in hashes.items():
        if len(hash_set) > 1:
            non_reproducible.append(wheel_name)

    if non_reproducible:
        raise AssertionError(f"Wheels are not reproducible: {non_reproducible}")
