import os
import shutil
from pathlib import Path

import pytest


if "TESTWHEEL_GENERATE_PATH" not in os.environ:
    pytest.skip(allow_module_level=True)


def test_store_patched_wheel(patched_wheel: Path) -> None:
    out_dir = Path(os.environ["TESTWHEEL_GENERATE_PATH"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / patched_wheel.name
    shutil.copy(patched_wheel, out_file)
