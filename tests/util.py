import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename


def _call_new_python(context, *py_args, **kwargs) -> bytes:
    # Copied from stdlib venv module, but this version returns the output.
    env_exec_cmd = context.env_exe
    if sys.platform == "win32":
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


def is_wheel_compatible(wheel: Path) -> bool:
    _, _, _, wheel_tags = parse_wheel_filename(wheel.name)
    for sys_tag in sys_tags():
        if sys_tag in wheel_tags:
            return True
    return False


def check_wheel_installs_and_runs(wheel: Path) -> None:
    """Returns False if the wheel is not for the current platform."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = venv.EnvBuilder(with_pip=True)
        env.create(tmpdir)
        context = env.ensure_directories(tmpdir)
        _call_new_python(context, "-m", "pip", "install", str(wheel))
        answer = _call_new_python(context, "-c", "from repairwheel_test import testwheel; print(testwheel.get_answer())")
        assert answer.strip() == b"42"
        doc = _call_new_python(context, "-c", "from repairwheel_test import testwheel; print(testwheel.__doc__)")
        assert doc.strip() == b"A test wheel."

    return True
