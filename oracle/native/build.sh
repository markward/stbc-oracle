#!/bin/sh
# Build the four native capture plugins (32-bit Windows DLLs named .asi) with MinGW-w64.
#   macOS:  brew install mingw-w64      Linux: apt install gcc-mingw-w64-i686
# Output: oracle/native/out/*.asi -- copy the ones you want into the oracle copy of the game
# (see README.md), next to stbc.exe and an ASI loader.
set -e
cd "$(dirname "$0")"
CC=${CC:-i686-w64-mingw32-gcc}
MH="minhook/src/buffer.c minhook/src/hook.c minhook/src/trampoline.c minhook/src/hde/hde32.c"
mkdir -p out
for p in combattap:CombatTap lockstep:Lockstep randtap:RandTap oracleassist:OracleAssist; do
    src=${p%%:*}; name=${p#*:}
    $CC -O2 -shared -static-libgcc -I. -o "out/$name.asi" "$src/$src.c" $MH -ldxguid
    echo "built out/$name.asi"
done
