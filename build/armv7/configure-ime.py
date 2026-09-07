#!/usr/bin/env python3
"""Reject unrepresentable IME replacement ranges before Blink's checked casts."""
import argparse
import os
from pathlib import Path

RELATIVE_PATH = Path('third_party/blink/renderer/core/frame/web_frame_widget_impl.cc')
MARKER = 'WEBOS_CHROMIUM_IME_RANGE_GUARD'
ANCHOR = '''  if (!controller)
    return false;

  return controller->SetComposition(
'''
REPLACEMENT = '''  if (!controller)
    return false;

  // WEBOS_CHROMIUM_IME_RANGE_GUARD: a wrapped platform deletion range must
  // cancel composition, not trap in checked_cast or overflow WebRange's end.
  // InvalidRange retains its existing "no replacement" meaning.
  if (replacement_range.IsValid()) {
    constexpr size_t kMaxWebRangeOffset = std::numeric_limits<int>::max();
    const size_t range_start = replacement_range.start();
    const size_t range_length = replacement_range.length();
    if (range_start > kMaxWebRangeOffset ||
        range_length > kMaxWebRangeOffset - range_start) {
      return false;
    }
  }

  return controller->SetComposition(
'''


def patch_source(source):
    if MARKER in source:
        if source.count(REPLACEMENT) != 1 or source.count('#include <limits>') != 1:
            raise RuntimeError('IME guard marker exists without the expected complete patch')
        return source
    if source.count(ANCHOR) != 1:
        raise RuntimeError('IME guard requires one exact SetComposition anchor')
    if '#include <limits>' not in source:
        if source.count('#include <memory>') != 1:
            raise RuntimeError('IME guard requires one exact standard-include anchor')
        source = source.replace('#include <memory>', '#include <limits>\n#include <memory>')
    return source.replace(ANCHOR, REPLACEMENT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path,
                        default=Path(os.environ.get('WEBOS_CHROMIUM_SRC', '/build/chromium120/src')))
    args = parser.parse_args()
    path = args.source_root / RELATIVE_PATH
    before = path.read_text()
    after = patch_source(before)
    if after != before:
        path.write_text(after)
    print('IME replacement range guard verified')


if __name__ == '__main__':
    main()
