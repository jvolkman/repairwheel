import os
import platform
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

import pytest
from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename


def _call_new_python(context, *py_args, **kwargs) -> bytes:
    # Copied from stdlib venv module, but this version returns the output.
    env_exec_cmd = context.env_exe
    if sys.platform == 'win32':
        real_env_exe = os.path.realpath(context.env_exe)
        if os.path.normcase(real_env_exe) != os.path.normcase(context.env_exe):
            context.env_exec_cmd = real_env_exe

    args = [env_exec_cmd, *py_args]
    kwargs["env"] = env = os.environ.copy()
    env["VIRTUAL_ENV"] = context.env_dir
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    kwargs["cwd"] = context.env_dir
    kwargs["executable"] = env_exec_cmd
    return subprocess.check_output(args, **kwargs)


def test_wheel_contains_testdep(patched_wheel: Path) -> None:
    with zipfile.ZipFile(patched_wheel, "r") as zf:
        for file in zf.filelist:
            if "testdep" in file.filename.lower():
                break
        else:
            assert False, f"testdep not found in wheel: {patched_wheel}"


def test_wheel_installs_and_runs(patched_wheel: Path) -> None:
    _, _, _, wheel_tags = parse_wheel_filename(patched_wheel.name)
    for sys_tag in sys_tags():
        if sys_tag in wheel_tags:
            break
    else:
        pytest.skip(f"Wheel not installable on {platform.platform()}: {patched_wheel.name}")

    with tempfile.TemporaryDirectory() as tmpdir:
        env = venv.EnvBuilder(with_pip=True)
        env.create(tmpdir)
        context = env.ensure_directories(tmpdir)
        _call_new_python(context, "-m", "pip", "install", str(patched_wheel))
        answer = _call_new_python(context, "-c", "from repairwheel_test import testwheel; print(testwheel.get_answer())")
        assert answer.strip() == b"42"
        doc = _call_new_python(context, "-c", "from repairwheel_test import testwheel; print(testwheel.__doc__)")
        assert doc.strip() == b"A test wheel."
