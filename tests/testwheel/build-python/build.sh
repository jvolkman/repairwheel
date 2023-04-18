#!/bin/sh

set -e

rm -rf dist
flit build
mkdir -p ../py3-none-any
cp dist/*.whl ../py3-none-any
