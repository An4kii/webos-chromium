#!/usr/bin/env bash
set -euo pipefail
mkdir -p /build/diagnostics
for log in /build/logs/*.log; do
  [[ -f "$log" ]] || continue
  tail -n5000 "$log" > "/build/diagnostics/$(basename "$log")"
done
if [[ -d /build/state ]]; then
  cp -a /build/state /build/diagnostics/state
fi
if [[ -f /build/out/armv7/args.gn ]]; then
  cp /build/out/armv7/args.gn /build/diagnostics/
fi
dpkg-query -W > /build/diagnostics/packages.txt
df -h /build > /build/diagnostics/disk.txt
free -m > /build/diagnostics/memory.txt
