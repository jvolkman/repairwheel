# repairwheel

This project aims to be a combination of `auditwheel`, `delocate`, and `delvewheel` written in pure Python and able to run cross-platform.

Very much a WIP.

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
