#!/usr/bin/env python3
"""Generate explicit GN settings for the public SDK and bounded local runtime."""
from pathlib import Path
import json
import subprocess
src = Path('/build/chromium120/src')
recipe = Path('/build/recipe')
llvm = src/'third_party/llvm-build/Release+Asserts/bin'
sdk = Path('/build/sdk')
gcc = sdk/'bin/arm-webos-linux-gnueabi-gcc'
sysroot = subprocess.check_output([str(gcc), '-print-sysroot'],text=True).strip()
gcclib = str(Path(subprocess.check_output([str(gcc), '-print-libgcc-file-name'],text=True).strip()).resolve().parent)
arm = f'--target=arm-linux-gnueabi -B{gcclib} -march=armv7-a -mfloat-abi=softfp -mfpu=neon-fp16'
# These values are ARM Linux UAPI definitions absent in the old SDK headers.
compat = ('-D_GNU_SOURCE -D_LIBCPP_HAS_NO_C11_ALIGNED_ALLOC '
          '-D__NR_getrandom=384 -D__NR_memfd_create=385 -DSYS_memfd_create=385 '
          '-DAT_HWCAP2=26 -DHWCAP2_AES=1 -DHWCAP2_PMULL=2 -DHWCAP2_SHA1=4 '
          '-DHWCAP2_SHA2=8 -DHWCAP2_CRC32=16 -DF_GET_SEALS=1034 -DF_ADD_SEALS=1033 '
          '-DF_SEAL_SEAL=1 -DF_SEAL_SHRINK=2 -DF_SEAL_GROW=4 '
          '-DSIOCGSTAMP_OLD=0x8906 -DSIOCGSTAMPNS_OLD=0x8907 -DO_TMPFILE=020400000')
includes = ' '.join('-I'+str(src/p) for p in (
    'third_party/vulkan-deps/vulkan-headers/src/include', 'third_party/wayland/src/src',
    'third_party/wayland/include', 'third_party/wayland/src/egl',
    'third_party/wayland/src/cursor', 'third_party/abseil-cpp'))
args = {}
for line in (recipe/'vendor/args.gn.in').read_text().splitlines():
    if ' = ' in line:
        name,value = line.split(' = ',1)
        args[name] = value

def setarg(name,value):
    args[name] = json.dumps(value)

for name,value in {
    'is_official_build':False, 'use_thin_lto':False, 'concurrent_links':1,
    'v8_snapshot_toolchain':'//build/toolchain/linux:clang_x86_v8_arm',
    'clang_base_path':str(llvm.parent),
    'cros_host_cc':str(recipe/'clang-host-webos'),
    'cros_host_cxx':str(recipe/'clang++-host-webos'),
    'cros_host_ld':str(recipe/'clang++-host-webos'),
    'cros_host_nm':str(llvm/'llvm-nm'),
    'cros_host_sysroot':'/', 'cros_host_system_libdir':'lib/x86_64-linux-gnu',
    'host_pkg_config':str(recipe/'host-pkg-config'),
    'cros_host_pkg_config':str(recipe/'host-pkg-config'),
    'cros_target_cc':str(recipe/'clang-webos'),
    'cros_target_cxx':str(recipe/'clang++-webos'),
    'cros_target_ld':str(recipe/'clang++-webos'),
    'cros_target_ar':str(llvm/'llvm-ar'),
    'cros_target_nm':str(llvm/'llvm-nm'),
    'cros_target_readelf':str(llvm/'llvm-readelf'),
    'cros_target_extra_cppflags':f'{arm} {compat} {includes}',
    'cros_target_extra_cflags':arm,
    'cros_target_extra_asmflags':arm,
    'cros_target_extra_ldflags':f'--target=arm-linux-gnueabi -fuse-ld=lld -rtlib=libgcc -B{gcclib} -L{gcclib} -lglibc_polyfills -ldl',
    'target_sysroot':sysroot, 'use_custom_libcxx':True,
    'use_custom_libcxx_for_host':False, 'enable_pwa_manager_webapi':False,
    'use_nss_certs':False, 'enable_swiftshader':False,
}.items():
    setarg(name,value)
out = Path('/build/out/armv7')
out.mkdir(parents=True,exist_ok=True)
text='\n'.join(f'{name} = {value}' for name,value in args.items())+'\n'
assert '@' not in text
(out/'args.gn').write_text(text)
print(f'GN args ready: {out}/args.gn')
