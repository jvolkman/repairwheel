# repairwheel

[![CI - Test](https://github.com/jvolkman/repairwheel/actions/workflows/test.yml/badge.svg)](https://github.com/jvolkman/repairwheel/actions/workflows/test.yml)
[![PyPI - Version](https://img.shields.io/pypi/v/repairwheel.svg?logo=pypi&label=PyPI&logoColor=gold)](https://pypi.org/project/repairwheel/)

## Overview

- `repairwheel` combines the "repair" steps from [`auditwheel`](https://github.com/pypa/auditwheel), [`delocate`](https://github.com/matthew-brett/delocate),
  and [`delvewheel`](https://github.com/adang1345/delvewheel) into a single tool, enabling cross-platform wheel repair.
- It includes pure-python replacements for external tools like `patchelf`, `otool`, `install_name_tool`, and `codesign`, so no non-python dependencies are required.

## What's it do?

1. When invoked, `repairwheel` first looks at the platform tag on the input wheel.
2. Based on the tag, `repairwheel` selects a repair step from `auditwheel`, `delocate`, or `delvewheel` (or nothing, if it's a pure-Python wheel)
3. Finally, `repairwheel` rewrites the result in a canonical form ensuring that:
   1. File timestamps are set to a constant value;
   2. Files in the archive are ordered lexicographically; and
   3. Files in `RECORD` are ordered lexicographically

The final result _should_ be bitwise-identitcal regardless of the system used to perform the repair.

## Usage

```
usage: repairwheel [-h] -o OUTPUT_DIR [-l LIB_DIR] wheel

positional arguments:
  wheel

options:
  -h, --help            show this help message and exit
  -o OUTPUT_DIR, --output-dir OUTPUT_DIR
  -l LIB_DIR, --lib-dir LIB_DIR
```

## Example

```shell
$ repairwheel \
  tests/testwheel/cp36-abi3-macosx_10_11_arm64/testwheel-0.0.1-cp36-abi3-macosx_10_11_arm64.whl \
  -l tests/testwheel/cp36-abi3-macosx_10_11_arm64/lib \
  -o /tmp/wheelout

$ repairwheel \
  tests/testwheel/cp36-abi3-linux_x86_64/testwheel-0.0.1-cp36-abi3-linux_x86_64.whl \
  -l tests/testwheel/cp36-abi3-linux_x86_64/lib \
  -o /tmp/wheelout

$ ls /tmp/wheelout
testwheel-0.0.1-cp36-abi3-macosx_10_11_arm64.whl
testwheel-0.0.1-cp36-abi3-manylinux_2_5_x86_64.manylinux1_x86_64.whl
```
