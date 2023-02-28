import os
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

import pytest


def _call_new_python(context, *py_args, **kwargs) -> bytes:
    """Executes the newly created Python using safe-ish options"""
    # Copied from stdlib venv module.
    args = [context.env_exec_cmd, *py_args]
    kwargs['env'] = env = os.environ.copy()
    env['VIRTUAL_ENV'] = context.env_dir
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    kwargs['cwd'] = context.env_dir
    kwargs['executable'] = context.env_exec_cmd
    return subprocess.check_output(args, **kwargs)


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

    with tempfile.TemporaryDirectory() as tmpdir:
        env = venv.EnvBuilder(with_pip=True)
        env.create(tmpdir)
        context = env.ensure_directories(tmpdir)
        _call_new_python(context, "-m", "pip", "install", str(patched_wheel))
        answer = _call_new_python(context, "-c", "from repairwheel_test import testwheel; print(testwheel.get_answer())")
        assert answer.strip() == b'42'
