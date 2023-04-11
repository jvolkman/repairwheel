import os
import platform
from pathlib import Path

import pytest

from ..util import check_wheel_installs_and_runs, is_wheel_compatible

GEN_PATH = os.environ.get("TESTWHEEL_GENERATE_PATH")

if GEN_PATH is None:
    pytest.skip(allow_module_level=True)


@pytest.mark.parametrize(
    "patched_wheel",
    Path(GEN_PATH).glob("**/*.whl"),
    ids=lambda p: os.path.relpath(str(p), GEN_PATH),
)
def test_check_patched_wheel(patched_wheel: Path) -> None:
    if not is_wheel_compatible(patched_wheel):
        pytest.skip(f"Wheel not installable on {platform.platform()}: {patched_wheel.name}")
    check_wheel_installs_and_runs(patched_wheel)
