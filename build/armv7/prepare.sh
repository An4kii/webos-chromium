#!/usr/bin/env bash
set -euo pipefail
mkdir -p /build/downloads /build/logs /build/state
exec > >(tee -a /build/logs/prepare.log) 2>&1
trap 'rc=$?; echo "prepare exit=$rc $(date -u +%FT%TZ)"; exit "$rc"' EXIT
PIN=e6a73fffdbe3bcc6f7fc33316c74adc6e7c01853
SDK=arm-webos-linux-gnueabi_sdk-buildroot-x86_64.tar.gz
fetch() {
  local url=$1 dest=$2
  if [[ ! -f "$dest.complete" ]]; then
    curl --fail --location --retry 8 --retry-delay 5 --connect-timeout 30 --speed-time 120 --speed-limit 1024 --continue-at - --output "$dest" "$url"
    sha256sum "$dest" | tee "$dest.sha256"
    touch "$dest.complete"
  fi
}
echo "Prepare started $(date -u +%FT%TZ)"
df -h /build
[[ $(df -Pk /build | awk 'NR==2 {print $4}') -gt 70000000 ]] || { echo "Insufficient build disk headroom"; exit 20; }
fetch "https://github.com/openlgtv/buildroot-nc4/releases/download/webos-a38c582/$SDK" "/build/downloads/$SDK"
printf '%s  %s\n' 04ad3311b48b4557a7002aef56ae2e167478e8e129f37daac04649bddf813616 "/build/downloads/$SDK" | sha256sum -c -
if [[ ! -f /build/state/sdk-extracted ]]; then
  mkdir -p /build/sdk
  tar -xzf "/build/downloads/$SDK" -C /build/sdk --strip-components=1
  (cd /build/sdk && ./relocate-sdk.sh)
  touch /build/state/sdk-extracted
fi
/build/sdk/bin/arm-webos-linux-gnueabi-gcc --version
/build/sdk/bin/arm-webos-linux-gnueabi-gcc -print-sysroot
fetch "https://codeload.github.com/webosose/chromium120/tar.gz/$PIN" "/build/downloads/chromium120-$PIN.tar.gz"
printf '%s  %s\n' 3adc0c84ad600909253418a45a0b66ce0aa8f992101e01a75a40671bfc6b440b "/build/downloads/chromium120-$PIN.tar.gz" | sha256sum -c -
if [[ ! -f /build/state/source-extracted ]]; then
  mkdir -p /build/chromium120
  [[ $(df -Pk /build | awk 'NR==2 {print $4}') -gt 60000000 ]] || { echo "Insufficient source extraction headroom"; exit 20; }
  tar -xzf "/build/downloads/chromium120-$PIN.tar.gz" -C /build/chromium120 --strip-components=1
  touch /build/state/source-extracted
fi
python3 - <<'VERIFY'
from pathlib import Path
p=Path('/build/chromium120/src/chrome/VERSION')
assert p.read_text().splitlines()==['MAJOR=120','MINOR=0','BUILD=6099','PATCH=269'],p.read_text()
VERIFY
# This public repository is a vendored snapshot. Its .gclient refers to private
# LG infrastructure; gclient sync/hooks are intentionally never invoked.
echo "$PIN" > /build/state/source-pin
file /build/chromium120/src/third_party/llvm-build/Release+Asserts/bin/clang
du -sh /build/chromium120 /build/sdk
printf 'source and SDK ready %s\n' "$(date -u +%FT%TZ)"
touch /build/state/prepared
