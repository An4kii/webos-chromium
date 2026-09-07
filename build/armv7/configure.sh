#!/usr/bin/env bash
set -euo pipefail
[[ -f /build/state/prepared ]]
mkdir -p /build/logs /build/recipe
exec > >(tee -a /build/logs/configure.log) 2>&1
export WEBOS_CHROMIUM_SRC=/build/chromium120/src
SRC=$WEBOS_CHROMIUM_SRC
SYSROOT=$(/build/sdk/bin/arm-webos-linux-gnueabi-gcc -print-sysroot)
LLVM=$SRC/third_party/llvm-build/Release+Asserts/bin
for tool in clang clang++ llvm-ar llvm-nm llvm-readelf ld.lld; do
  test -x "$LLVM/$tool"
done
"$LLVM/clang" --version
# Use distro multilib for the 32-bit V8 simulator executable, no private sysroot.
printf '#include <stdio.h>\nint main(){puts("clang-i386-ok");}\n' > /build/state/compiler-smoke.c
"$LLVM/clang" -m32 /build/state/compiler-smoke.c -o /build/state/clang-i386
/build/state/clang-i386
"$LLVM/clang" --target=arm-linux-gnueabi --sysroot="$SYSROOT" \
  -B"$(dirname "$(/build/sdk/bin/arm-webos-linux-gnueabi-gcc -print-libgcc-file-name)")" \
  -L"$(dirname "$(/build/sdk/bin/arm-webos-linux-gnueabi-gcc -print-libgcc-file-name)")" \
  -march=armv7-a -mfloat-abi=softfp -mfpu=neon -fuse-ld=lld \
  /build/state/compiler-smoke.c -o /build/state/clang-armv7
file /build/state/clang-armv7
readelf -l /build/state/clang-armv7 | sed -n '/interpreter/p'
for name in clang-webos clang++-webos clang-host-webos clang++-host-webos; do
  ln -sfn clang-webos-wrapper "/build/recipe/$name"
done
chmod +x /build/recipe/clang-webos-wrapper /build/recipe/host-pkg-config
# Same small architecture-independent UAPI overlay required by the cited recipe.
for header in videodev2.h memfd.h kcmp.h libc-compat.h if.h wireless.h net.h netlink.h sockios.h socket.h input.h input-event-codes.h hdlc/ioctl.h; do
  mkdir -p "$(dirname "$SYSROOT/usr/include/linux/$header")"
  cmp -s "/usr/include/linux/$header" "$SYSROOT/usr/include/linux/$header" || \
    cp "/usr/include/linux/$header" "$SYSROOT/usr/include/linux/$header"
done
# The overlaid Linux memfd.h includes this architecture-independent encoding
# header, absent from the older SDK. Keep it from the same UAPI package.
mkdir -p "$SYSROOT/usr/include/asm-generic"
cmp -s /usr/include/asm-generic/hugetlb_encode.h "$SYSROOT/usr/include/asm-generic/hugetlb_encode.h" || \
  cp /usr/include/asm-generic/hugetlb_encode.h "$SYSROOT/usr/include/asm-generic/hugetlb_encode.h"
python3 - "$SYSROOT" <<'PTRACE'
from pathlib import Path
import sys
p=Path(sys.argv[1])/'usr/include/sys/ptrace.h'
s=p.read_text()
for name,value in [('PTRACE_GET_THREAD_AREA','22'),('PTRACE_GETVFPREGS','27'),('PTRACE_GETREGSET','0x4204')]:
    if name not in s:
        anchor='PTRACE_SETFPXREGS = 19,'
        assert s.count(anchor)==1, 'Unrecognized old ptrace header'
        s=s.replace(anchor,anchor+'\n  '+name+' = '+value+',')
    alias='#define '+name+' '+name
    if alias not in s:
        s=s.replace('__END_DECLS',alias+'\n__END_DECLS')
if p.read_text() != s:
    p.write_text(s)
PTRACE
python3 /build/recipe/configure-source.py
python3 /build/recipe/configure-ime.py
python3 /build/recipe/configure-media-diagnostics.py
python3 /build/recipe/configure-buffering-diagnostics.py
python3 /build/recipe/configure-presentation-diagnostics.py
python3 /build/recipe/configure-args.py
"$SRC/buildtools/linux64/gn" --root="$SRC" gen /build/out/armv7 --fail-on-unused-args
touch /build/state/configured
