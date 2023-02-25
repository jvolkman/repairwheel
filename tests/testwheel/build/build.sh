#!/bin/sh

CC="gcc"

rm -rf _build

mkdir _build
cp -r * _build
cd _build

cd testdep

"$CC" -shared -o libtestdep.so testdep.c

cd ..

pyproject-build -w
