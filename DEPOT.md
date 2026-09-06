# One-off Chromium 120 ARM32 build on Depot CI

This workflow uses a 64-CPU, 256-GB x86_64 Depot CI sandbox to cross-compile
Chromium 120.0.6099.269 for ARMv7 webOS. Its Ubuntu 22.04 job container matches
the build environment already used for the local build. No cloud-provider
account, GitHub organization, or imported TV credentials are used by this recipe.
Git is updated from the [Git project's documented Ubuntu PPA](https://git-scm.com/install/linux)
before checkout: Depot's local-patch step requires `git apply --allow-empty`,
which Ubuntu 22.04's original Git 2.34 does not support. The workflow checks that
exact operation before proceeding.

## Start from the prepared checkout

The Depot CLI must already be authenticated and the Depot Code Access app must
have access to this repository. Check without starting any compute:

```sh
depot ci migrate preflight --yes
```

Start one build and follow its output:

```sh
depot ci run --workflow .depot/workflows/chromium-armv7.yml --follow
```

This is a cloud execution command. The CLI uploads local tracked changes and
applies them after checkout; a GitHub push is optional. All helper files in this
checkout are committed so that they are included. If you edit or add helpers,
stage them with Git before running. There are no push or schedule triggers and
no automatic build retries.

Depot prints the run ID and dashboard URL. No custom job or step timeout is
configured; Depot's trial limits and any platform defaults still apply.
The 64-CPU size consumes included minutes at 32 times elapsed time; a
20,000-minute CI trial allocation would cover 625 elapsed minutes. Check the
actual account allocation; Docker build minutes and CI minutes are separate.

The current [pricing](https://depot.dev/pricing) advertises a seven-day trial.
The [CI size table](https://depot.dev/docs/ci/overview) documents the label and
usage multiplier. No subscription is changed by the preparation of these files.

## Collect the result

```sh
depot ci status RUN_ID
depot ci artifacts list RUN_ID
depot ci artifacts download ARTIFACT_ID --output-file chromium120-armv7.zip
```

Replace `RUN_ID` and `ARTIFACT_ID` with the values printed by Depot. The
`chromium120-armv7` artifact contains `chromium120-armv7.tar.gz` and its SHA-256
file. The separate diagnostics artifact contains bounded logs, GN arguments,
compiler package versions and stage status. It remains available when a build
fails before export, provided the final collection steps can run. Artifacts
request seven days' retention; download the browser promptly and preserve an
independent backup.

To stop a run early:

```sh
depot ci cancel RUN_ID
```

The source, object files and SDK live only inside the disposable CI job; they
are not uploaded as artifacts or copied to the Mac. A failed or timed-out job
does not retain a compiler cache for the next run. The existing Mac build is
independent and may continue while this job is evaluated.

## Build inputs and scope

- Recipe base: `cfernande1470/webos-chromium` at
  `b1e008f18442dd40166136568f9c126dcb8f595b`.
- LG source snapshot: `webosose/chromium120` at
  `e6a73fffdbe3bcc6f7fc33316c74adc6e7c01853`. The source archive SHA-256 is
  `3adc0c84ad600909253418a45a0b66ce0aa8f992101e01a75a40671bfc6b440b`.
- Public webOS SDK: `openlgtv/buildroot-nc4`, release `webos-a38c582`, ARM
  `gnueabi` SDK hosted on x86_64. Archive SHA-256:
  `04ad3311b48b4557a7002aef56ae2e167478e8e129f37daac04649bddf813616`.
- Bundled Clang/LLD, i386 V8 snapshot toolchain and custom target libc++.
- ARMv7 softfp with NEON; GN has one concurrent link and no thin LTO.
- Includes the checked source/host/locales/ARM CRC fixes and the matching UAPI
  `hugetlb_encode.h` overlay required by `linux/memfd.h`.

The source already vendors dependencies; do not invoke `gclient sync` or hooks
that refer to private LG infrastructure. Download hashes, compiler smoke tests,
minimum disk/inode capacity, requested CPU capacity, and RAM are checked before
the main compile. The cloud disk allocation is measured at runtime instead of
assuming the different Depot GitHub Actions runner disk specification.

This exports a runtime candidate for later native TV testing. It is not an IPK
installer or proof of working browser rendering, audio/video, DRM or sandboxing.
SDK EGL/GLES/Wayland graphics link stubs are excluded from the runtime export.
