#!/usr/bin/env bash
set -euo pipefail
JOBS=${JOBS:-64}
[[ "$JOBS" =~ ^[1-9][0-9]*$ && "$JOBS" -le 64 ]] || { echo 'JOBS must be between 1 and 64' >&2; exit 2; }
[[ "$JOBS" -le $(nproc) ]] || { echo 'JOBS exceeds available CPUs' >&2; exit 2; }
# Reserve at least 2 GiB per compile job; GN keeps its link pool at one.
memory_kib=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
[[ "$memory_kib" -ge $((JOBS * 2 * 1024 * 1024)) ]] || { echo 'Insufficient available RAM for requested compile jobs' >&2; exit 2; }
[[ -f /build/state/configured ]]
mkdir -p /build/logs
exec > >(tee -a /build/logs/build.log) 2>&1
ninja_pid=''
guard_pid=''
finish() {
  local rc=$?
  trap - EXIT
  if [[ -n "$ninja_pid" ]] && kill -0 "$ninja_pid" 2>/dev/null; then
    kill -TERM -- "-$ninja_pid" 2>/dev/null || true
  fi
  if [[ -n "$guard_pid" ]]; then
    kill "$guard_pid" 2>/dev/null || true
    wait "$guard_pid" 2>/dev/null || true
  fi
  printf '%s exit=%s\n' "$(date -u +%FT%TZ)" "$rc" > /build/state/build-result
  exit "$rc"
}
trap finish EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
export WEBOS_CHROMIUM_SRC=/build/chromium120/src
export PATH=/build/recipe:$PATH
[[ $(df -Pk /build | awk 'NR==2 {print $4}') -gt 15000000 ]] || { echo 'Insufficient build/link headroom'; exit 20; }
echo "Build started $(date -u +%FT%TZ), compile jobs=$JOBS, link jobs=1"
printf '%s\n' "$JOBS" > /build/state/compile-jobs
free -m
df -h /build
run_ninja() {
  setsid ninja -C /build/out/armv7 -j"$JOBS" "$@" &
  ninja_pid=$!
  (
    while kill -0 "$ninja_pid" 2>/dev/null; do
      if [[ $(df -Pk /build | awk 'NR==2 {print $4}') -lt 15000000 ]]; then
        echo 'Build stopped to preserve 15GiB disk headroom'
        touch /build/state/disk-headroom-stop
        kill -TERM -- "-$ninja_pid"
        exit
      fi
      sleep 30
    done
  ) &
  guard_pid=$!
  result=0
  wait "$ninja_pid" || result=$?
  kill "$guard_pid" 2>/dev/null || true
  wait "$guard_pid" 2>/dev/null || true
  ninja_pid=''
  guard_pid=''
  return "$result"
}
# Avoid the upstream order-only Wayland dependency reaching the final link first.
run_ninja wayland_client
run_ninja browser_shell_webos
file /build/out/armv7/browser_shell_webos /build/out/armv7/libcbe.so
touch /build/state/linked
