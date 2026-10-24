#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
target=${1:-all}
case "$target" in all) targets='linux-x86_64 keenetic-arm64';; linux-x86_64|keenetic-arm64) targets=$target;; *) echo 'usage: build.sh [all|linux-x86_64|keenetic-arm64]' >&2; exit 2;; esac
for target in $targets; do
 case "$target" in
  linux-x86_64) compiler=${CC_X86_64:-gcc}; flags='-O3 -mtune=generic'; arch=linux/amd64; output=wgot-server;;
  keenetic-arm64) compiler=${CC_ARM64:-aarch64-linux-gnu-gcc}; flags='-O3 -mcpu=cortex-a53'; arch=linux/arm64; output=wgot-client;;
 esac
 command -v "$compiler" >/dev/null
 build="$ROOT/build/$target"
 dest="$ROOT/dist/$target"
 mkdir -p "$build" "$dest"
 cp "$ROOT"/src/*.c "$ROOT"/src/*.h "$ROOT/src/Makefile" "$build/"
 make -C "$build" clean
 make -C "$build" RELEASE=1 CC="$compiler" CFLAGS="$flags -Wall -pthread -DWGOT_MMSG" LDFLAGS='-static -s -pthread' TARGETPLATFORM="$arch" COMMIT=7008e0ce
 cp "$build/wg-obfuscator" "$dest/$output"
 chmod 755 "$dest/$output"
 cp "$ROOT/LICENSE" "$dest/LICENSE"
 "$compiler" --version | head -1 > "$dest/compiler.txt"
done
(cd "$ROOT" && find dist -type f ! -name SHA256SUMS -exec sha256sum {} \; | sort > dist/SHA256SUMS)
