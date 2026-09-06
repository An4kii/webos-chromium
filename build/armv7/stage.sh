#!/usr/bin/env bash
set -euo pipefail
recipe=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
[[ $(uname -m) == x86_64 ]] || { echo 'An x86_64 Linux builder is required'; exit 2; }
[[ $(nproc) -ge 64 ]] || { echo 'Expected the requested 64-CPU sandbox'; exit 2; }
[[ $(awk '/^MemAvailable:/ {print $2}' /proc/meminfo) -ge 134217728 ]] || { echo 'Need at least 128 GiB available RAM for 64 compile jobs'; exit 2; }
[[ ! -e /build ]] || { echo '/build already exists; refusing to reuse unrelated data'; exit 2; }
mkdir -p /build/recipe /build/state /build/logs
cp -a "$recipe/." /build/recipe/
chmod +x /build/recipe/clang-webos-wrapper /build/recipe/host-pkg-config
repository=$(git -C "$recipe" rev-parse --show-toplevel)
git -C "$repository" rev-parse HEAD > /build/state/recipe-git-head
git -C "$repository" diff --binary HEAD -- build/armv7 .depot/workflows > /build/state/recipe-local-changes.patch
uname -a > /build/state/build-host.txt
df -h /build
df -i /build
# CI disk capacity is checked at runtime; Actions runner disk sizes are different.
[[ $(df -Pk /build | awk 'NR==2 {print $4}') -gt 70000000 ]] || { echo 'Need at least 70,000,000 KiB free before downloading Chromium'; exit 20; }
[[ $(df -Pi /build | awk 'NR==2 {print $4}') -gt 500000 ]] || { echo 'Need at least 500,000 free inodes'; exit 20; }
