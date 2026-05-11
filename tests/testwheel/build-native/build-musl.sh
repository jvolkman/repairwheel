#!/bin/sh
# Build the musl test wheel using an Alpine container.
# Requires docker or podman.
#
# Usage:
#   ./build-musl.sh <output-dir>
#
# Output:
#   <output-dir>/cp36-abi3-linux_x86_64_musl/testwheel-0.0.1-cp36-abi3-linux_x86_64.whl
#   <output-dir>/cp36-abi3-linux_x86_64_musl/lib/libtestdep.so

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="${1:?Usage: $0 <output-dir>}"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

CONTAINER_CMD="docker"
if ! command -v docker >/dev/null 2>&1; then
    CONTAINER_CMD="podman"
fi

WHEEL_DIR="$OUTPUT_DIR/cp36-abi3-linux_x86_64_musl"
mkdir -p "$WHEEL_DIR/lib"

# Build artifacts inside Alpine
TMPDIR=$(mktemp -d)
$CONTAINER_CMD run --rm \
    -v "$SCRIPT_DIR:/src:ro" \
    -v "$TMPDIR:/out" \
    alpine:latest sh -c '
set -e
apk add --quiet gcc musl-dev python3-dev

PYINC=$(python3 -c "import sysconfig; print(sysconfig.get_path(\"include\"))")

# Build testdep shared library
gcc -shared -fPIC -Wl,-soname,libtestdep.so \
    -o /out/libtestdep.so \
    /src/testdep/testdep.c -I/src/testdep

# Build Python extension linked against testdep (and dynamically against musl libc)
gcc -shared -fPIC \
    -I$PYINC -I/src/testdep \
    -L/out -Wl,--no-as-needed -ltestdep \
    -o /out/testwheel.abi3.so \
    /src/testwheel.c
'

# Copy lib
cp "$TMPDIR/libtestdep.so" "$WHEEL_DIR/lib/"

# Package into a wheel using build.py
cd "$SCRIPT_DIR"
python3 -c "
import sys; sys.path.insert(0, '.')
from build import LINUX_X86_64_MUSL_BUILD, build_wheel
from pathlib import Path
build_wheel(LINUX_X86_64_MUSL_BUILD, Path('$TMPDIR/testwheel.abi3.so'), None, Path('$WHEEL_DIR'))
"

rm -rf "$TMPDIR"

echo "Built: $(ls "$WHEEL_DIR"/*.whl)"
