#!/usr/bin/env python3
"""Apply the cited recipe's small source fixes with checked anchors."""
from pathlib import Path
import subprocess

root = Path('/build/chromium120')
src = root / 'src'
recipe = Path('/build/recipe')

def insert(path, anchor, replacement, marker):
    p = src / path
    text = p.read_text()
    if marker in text:
        return
    if text.count(anchor) != 1:
        raise RuntimeError(f'{path}: expected unique patch anchor, refusing blind edit')
    p.write_text(text.replace(anchor, replacement))

for name in ('0001-cross-build-host-and-locales.patch', '0002-disable-armv8-crc-on-armv7.patch'):
    patch = recipe / 'vendor' / name
    check = subprocess.run(['patch', '-p1', '--forward', '--dry-run', '-i', str(patch)], cwd=root, capture_output=True)
    if check.returncode == 0:
        subprocess.run(['patch', '-p1', '--forward', '-i', str(patch)], cwd=root, check=True)
    else:
        subprocess.run(['patch', '-p1', '--reverse', '--dry-run', '-i', str(patch)], cwd=root, check=True)

insert('net/cert/internal/system_trust_store.cc',
    'std::unique_ptr<SystemTrustStore> CreateEmptySystemTrustStore() {',
    '''// WEBOS_CHROMIUM_LINUX_TRUST_STORE: Chrome roots without Linux NSS.
#if BUILDFLAG(IS_LINUX)
std::unique_ptr<SystemTrustStore> CreateSslSystemTrustStoreChromeRoot(
    std::unique_ptr<TrustStoreChrome> chrome_root) {
  return std::make_unique<SystemTrustStoreChrome>(
      std::move(chrome_root), std::make_unique<TrustStoreCollection>());
}
#endif

std::unique_ptr<SystemTrustStore> CreateEmptySystemTrustStore() {''',
    'WEBOS_CHROMIUM_LINUX_TRUST_STORE')
insert('net/BUILD.gn', '  if (is_linux || is_chromeos || is_android) {\n    sources += [\n      "base/address_map_linux.cc",',
    '''  # WEBOS_CHROMIUM_LINUX_TEST_ROOTS
  if (is_linux && !use_nss_certs) {
    sources += [ "cert/test_root_certs_builtin.cc" ]
  }

  if (is_linux || is_chromeos || is_android) {
    sources += [
      "base/address_map_linux.cc",''', 'WEBOS_CHROMIUM_LINUX_TEST_ROOTS')
insert('webos/BUILD.gn', '    "//ui/gl",',
    '''    "//ui/gl",
    "//neva/browser_shell/service:shell_service",
    "//third_party/wayland:wayland_client",''', '//neva/browser_shell/service:shell_service')
insert('third_party/blink/renderer/platform/heap/thread_local.h', '#elif BUILDFLAG(IS_ANDROID)',
    '''#elif defined(OS_WEBOS)  // WEBOS_CHROMIUM_GLOBAL_TLS
#define BLINK_HEAP_THREAD_LOCAL_MODEL "global-dynamic"
#elif BUILDFLAG(IS_ANDROID)''', 'WEBOS_CHROMIUM_GLOBAL_TLS')
insert('webos/browser_shell/BUILD.gn', '    "browser_shell_webos_main_delegate.h",',
    '''    "browser_shell_webos_main_delegate.h",
    # WEBOS_CHROMIUM_BROWSER_SHELL_IMPL_SOURCES
    "//webos/common/webos_content_client.cc",
    "//webos/renderer/webos_content_renderer_client.cc",
    "//webos/renderer/webos_network_error_helper.cc",
    "//webos/renderer/webos_network_error_template_builder.cc",
    "//content/shell/common/shell_neva_switches.cc",
    "//neva/app_runtime/browser/app_runtime_browser_switches.cc",''', 'WEBOS_CHROMIUM_BROWSER_SHELL_IMPL_SOURCES')
p = src / 'webos/browser_shell/BUILD.gn'
s = p.read_text().replace('    "//webos:weboswebruntime"\n', '    "//webos:weboswebruntime",\n')
s = s.replace('    "//webos:webos_impl",\n', '').replace('    "//neva/app_runtime",\n', '')
if p.read_text() != s:
    p.write_text(s)
print('Source compatibility patches applied')
# The TV uses proprietary Mali EGL, with no Mesa DRI pkg-config metadata.
# All C++ DRI_DRIVER_DIR uses here are already guarded with defined().
insert('media/gpu/sandbox/BUILD.gn', '      !is_castos) {',
       '      !is_castos && !is_webos) {  # WEBOS_CHROMIUM_NO_MESA_DRI',
       'WEBOS_CHROMIUM_NO_MESA_DRI')
