#!/usr/bin/env python3
""" Apply patch to tree stored in wheel

Overwrites the wheel in-place by default
"""
# vim: ft=python
from __future__ import absolute_import, division, print_function

import os
from argparse import ArgumentParser
from os.path import basename, exists, expanduser
from os.path import join as pjoin

from repairwheel._vendor.delocate import patch_wheel
from repairwheel._vendor.delocate.cmd.common import common_parser, verbosity_config

parser = ArgumentParser(description=__doc__, parents=[common_parser])
parser.add_argument(
    "wheel", metavar="WHEEL", type=str, help="Wheel file to modify"
)
parser.add_argument(
    "patch_fname", metavar="PATCH", type=str, help="Patch file to apply"
)
parser.add_argument(
    "-w",
    "--wheel-dir",
    action="store",
    type=str,
    help="Directory to store patched wheel (default is to overwrite input)",
)


def main() -> None:
    args = parser.parse_args()
    verbosity_config(args)
    if args.wheel_dir:
        wheel_dir = expanduser(args.wheel_dir)
        if not exists(wheel_dir):
            os.makedirs(wheel_dir)
    else:
        wheel_dir = None
    if args.verbose:
        print("Patching: {0} with {1}".format(args.wheel, args.patch_fname))
    if wheel_dir:
        out_wheel = pjoin(wheel_dir, basename(args.wheel))
    else:
        out_wheel = args.wheel
    patch_wheel(args.wheel, args.patch_fname, out_wheel)
    if args.verbose:
        print("Patched wheel {0} to {1}:".format(args.wheel, out_wheel))


if __name__ == "__main__":
    main()
