#!/usr/bin/env python3
"""Log the webOS display scheduler and GL capabilities once on creation."""
import argparse
from pathlib import Path

PATCHES = (
    ('components/viz/service/frame_sinks/root_compositor_frame_sink_impl.cc',
     'WEBOS_CHROMIUM_BEGIN_FRAME_DIAGNOSTICS',
     '  const auto& capabilities = output_surface->capabilities();',
     '''
#if defined(OS_WEBOS)
  // WEBOS_CHROMIUM_BEGIN_FRAME_DIAGNOSTICS: describe the branch selected above.
  const char* begin_frame_kind = external_begin_frame_source_mojo ? "external_mojo"
      : params->disable_frame_rate_limit ? "back_to_back"
      : capabilities.supports_gpu_vsync ? "gpu_vsync" : "delay_based";
  LOG(INFO) << "CHROMIUM_PRESENTATION v=1 stage=begin_frame"
            << " source=" << begin_frame_kind
            << " gpu_compositing=" << (params->gpu_compositing ? 1 : 0)
            << " gpu_vsync=" << (capabilities.supports_gpu_vsync ? 1 : 0)
            << " max_pending_swaps=" << capabilities.pending_swap_params.max_pending_swaps;
#endif
'''),
    ('components/viz/service/display_embedder/skia_output_device_gl.cc',
     'WEBOS_CHROMIUM_SKIA_GL_DIAGNOSTICS',
     '  capabilities_.supports_gpu_vsync = gl_surface_->SupportsGpuVSync();',
     '''
#if defined(OS_WEBOS)
  // WEBOS_CHROMIUM_SKIA_GL_DIAGNOSTICS: no per-frame work or capability changes.
  LOG(INFO) << "CHROMIUM_PRESENTATION v=1 stage=skia_gl"
            << " gpu_vsync=" << (capabilities_.supports_gpu_vsync ? 1 : 0)
            << " async_swap=" << (supports_async_swap_ ? 1 : 0);
#endif
'''),
)


def patch_text(source, marker, anchor, insertion):
    replacement = anchor + insertion
    if marker in source:
        if source.count(replacement) != 1 or source.count(marker) != 1:
            raise RuntimeError('Incomplete or modified presentation diagnostic patch')
        return source
    if source.count(anchor) != 1:
        raise RuntimeError('Presentation diagnostic source anchor is not unique')
    source = source.replace(anchor, replacement)
    if '#include "base/logging.h"' not in source:
        include = '#include "base/time/time.h"'
        if source.count(include) != 1:
            raise RuntimeError('Presentation diagnostic include anchor is not unique')
        source = source.replace(include, '#include "base/logging.h"\n' + include)
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path('/build/chromium120/src'))
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    changes = []
    for relative, marker, anchor, insertion in PATCHES:
        path = args.source_root / relative
        before = path.read_text()
        after = patch_text(before, marker, anchor, insertion)
        if before != after:
            changes.append((path, after))
    if not args.check:
        for path, after in changes:
            path.write_text(after)
    print('CHROMIUM_PRESENTATION creation diagnostics verified')


if __name__ == '__main__':
    main()
