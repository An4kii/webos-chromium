#!/usr/bin/env bash
# Run inside the disposable Ubuntu 22.04 CI job container.
set -euo pipefail
[[ $(uname -m) == x86_64 ]] || { echo 'This SDK requires an x86_64 Linux host'; exit 2; }
[[ $(id -u) == 0 ]] || { echo 'Run in the root-owned disposable job container'; exit 2; }
export DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8
dpkg --add-architecture i386
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl git jq xz-utils bzip2 unzip file patch python3 python3-setuptools python3-pip \
  build-essential gcc-multilib g++-multilib pkg-config ninja-build binutils nasm gperf flex bison \
  libglib2.0-dev libnss3-dev libnspr4-dev libdbus-1-dev libexpat1-dev libfontconfig1-dev \
  libfreetype6-dev libdrm-dev libx11-dev libx11-xcb-dev libxcb1-dev libxcomposite-dev \
  libxcursor-dev libxdamage-dev libxext-dev libxfixes-dev libxi-dev libxrandr-dev libxrender-dev \
  libxss-dev libxtst-dev libasound2-dev libpulse-dev libudev-dev libpci-dev libcap-dev \
  libegl1-mesa-dev libgles2-mesa-dev libgbm-dev libxkbcommon-dev libwayland-dev \
  libc6-dev-i386 lib32gcc-11-dev lib32stdc++-11-dev libatomic1:i386 libglib2.0-0:i386 \
  libxml-parser-perl libjson-perl rsync time zstd procps util-linux
rm -rf /var/lib/apt/lists/*
