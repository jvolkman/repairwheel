import os
import subprocess
import sys
from pathlib import Path
from typing import List


def repair(wheel: Path, output_path: Path, lib_path: List[Path], verbosity: int = 0) -> None:
    args = [
        sys.executable,
        "-m",
        "delvewheel",
        "repair",
        str(wheel),
        "--wheel-dir",
        str(output_path),
        "--no-diagnostic",
    ]

    if lib_path:
        args.extend(
            [
                "--add-path",
                os.pathsep.join([str(p) for p in lib_path]),
            ]
        )

    subprocess.check_call(args, env=os.environ)
