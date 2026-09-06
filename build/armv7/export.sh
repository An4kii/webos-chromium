#!/usr/bin/env bash
# Export only runtime candidates + compact metadata; never deletes build inputs.
set -euo pipefail
OUT=/build/out/armv7
DEST=/build/export
[[ -f /build/state/linked ]] || { echo 'Browser link is not complete; nothing exported' >&2; exit 2; }
[[ -f "$OUT/browser_shell_webos" && -f "$OUT/libcbe.so" ]]
mkdir -p "$DEST/runtime/bin" "$DEST/runtime/lib" "$DEST/metadata"
python3 - <<'PY'
from pathlib import Path
import re,shutil,subprocess
out=Path('/build/out/armv7'); dst=Path('/build/export/runtime/bin')
for p in out.iterdir():
    # The initial native-Mali route uses TV graphics libraries. Do not let a
    # generated ANGLE or SDK link stub override them through this private path.
    if p.name.startswith(('libEGL.so','libGLES','libwayland','libvulkan')):
        continue
    if p.is_file() and (p.name in ('browser_shell_webos','libcbe.so') or p.suffix in ('.pak','.dat','.bin','.json') or re.search(r'\.so(?:\.\d+)*$', p.name)):
        shutil.copy2(p,dst/p.name)
    elif p.is_dir() and p.name in ('locales','neva_locales','resources'):
        shutil.copytree(p,dst/p.name,dirs_exist_ok=True)
needed=''.join(subprocess.check_output(['readelf','-d',str(out/name)],text=True)
               for name in ('browser_shell_webos','libcbe.so'))
if '[libffi.so.8]' in needed:
    ffi=Path('/build/sdk/arm-webos-linux-gnueabi/sysroot/usr/lib/libffi.so.8')
    assert ffi.resolve().is_file()
    shutil.copy2(ffi.resolve(),'/build/export/runtime/lib/libffi.so.8')
PY
cp "$OUT/args.gn" "$DEST/metadata/"
mkdir -p "$DEST/metadata/recipe"
cp -a /build/recipe/. "$DEST/metadata/recipe/"
cp /build/downloads/*.sha256 "$DEST/metadata/"
mkdir -p "$DEST/metadata/state"
cp -a /build/state/. "$DEST/metadata/state/"
dpkg-query -W > "$DEST/metadata/packages.txt"
file "$DEST/runtime/bin/browser_shell_webos" "$DEST/runtime/bin/libcbe.so" > "$DEST/metadata/elf-file.txt"
readelf -h -l -d -V "$DEST/runtime/bin/browser_shell_webos" > "$DEST/metadata/browser-elf.txt"
readelf -h -l -d -V "$DEST/runtime/bin/libcbe.so" > "$DEST/metadata/libcbe-elf.txt"
# Cap retained raw logs to the final 5000 lines per stage, preserving failures.
for log in /build/logs/*.log; do
  [[ -f "$log" ]] && tail -n5000 "$log" > "$DEST/metadata/$(basename "$log")"
done
(cd "$DEST/runtime" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$DEST/metadata/runtime-sha256.txt"
tar -C "$DEST" -czf "$DEST/chromium120-armv7.tar.gz" runtime metadata
(cd "$DEST" && sha256sum chromium120-armv7.tar.gz > chromium120-armv7.tar.gz.sha256)
echo 'Export ready. Copy archive + checksum to Mac and independent backup before parent cleanup.'
