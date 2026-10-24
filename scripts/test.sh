#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$ROOT/build/tests"
gcc -O1 -g -Wall -fsanitize=address,undefined -fno-omit-frame-pointer -I "$ROOT/src" "$ROOT/tests/codec-compat.c" "$ROOT/src/obfuscation.c" -o "$ROOT/build/tests/codec-compat"
for key in compatibility-key 0123456789abcdef0123456789abcdef AbCzYx9876543210-test; do
 "$ROOT/build/tests/codec-compat" "$key"
done
