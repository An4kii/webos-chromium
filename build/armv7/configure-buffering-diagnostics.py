#!/usr/bin/env python3
"""Expose Chromium's existing video-underflow classification without page data."""
import argparse
from pathlib import Path

TARGET = Path('media/renderers/video_renderer_impl.cc')
MARKER = 'WEBOS_CHROMIUM_BUFFERING_DIAGNOSTICS_V1'
ANCHOR = '''  media_log_->AddEvent<MediaLogEvent::kBufferingStateChanged>(
      SerializableBufferingState<SerializableBufferingStateType::kVideo>{
          buffering_state, reason});

  client_->OnBufferingStateChange(buffering_state, reason);'''
INSERTION = '''  // WEBOS_CHROMIUM_BUFFERING_DIAGNOSTICS_V1: existing state transitions only.
  // The reason distinguishes a pending demux read from a decoder-side shortage;
  // neither classification alone establishes the underlying performance cause.
  LOG(INFO) << "CHROMIUM_BUFFERING v=1 stream=video"
            << " player_id=" << player_id_
            << " state=" << static_cast<int>(buffering_state)
            << " reason_id=" << static_cast<int>(reason)
            << " reason=" << (reason == DEMUXER_UNDERFLOW ? "demuxer_underflow"
                              : reason == DECODER_UNDERFLOW ? "decoder_underflow"
                                                           : "unknown")
            << " playing=" << (state_ == kPlaying ? 1 : 0);

'''
REPLACEMENT = ANCHOR.replace('  client_->OnBufferingStateChange',
                             INSERTION + '  client_->OnBufferingStateChange')


def patch_text(source):
    if MARKER in source:
        if source.count(REPLACEMENT) != 1 or source.count(MARKER) != 1:
            raise RuntimeError('Incomplete or modified buffering diagnostics patch')
        return source
    if source.count(ANCHOR) != 1 or source.count('#include "base/location.h"') != 1:
        raise RuntimeError('Buffering diagnostics require unique pinned-source anchors')
    source = source.replace(ANCHOR, REPLACEMENT)
    if '#include "base/logging.h"' not in source:
        source = source.replace('#include "base/location.h"',
                                '#include "base/location.h"\n#include "base/logging.h"')
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path('/build/chromium120/src'))
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = args.source_root / TARGET
    before = path.read_text()
    after = patch_text(before)
    if after != before and not args.check:
        path.write_text(after)
    print('CHROMIUM_BUFFERING source patch verified' if args.check else
          'CHROMIUM_BUFFERING source patch applied')


if __name__ == '__main__':
    main()
