#!/usr/bin/env python3
"""Add selection-only, allowlisted stderr diagnostics to pinned Chromium 120.

Upstream: webosose/chromium120 e6a73fffdbe3bcc6f7fc33316c74adc6e7c01853
Target: src/media/filters/decoder_stream.cc, OnDecoderSelected().
No networking, decoder settings, per-frame work, or general media-log dumps.
"""

import argparse
from pathlib import Path


SOURCE_REVISION = "e6a73fffdbe3bcc6f7fc33316c74adc6e7c01853"
TARGET = Path("media/filters/decoder_stream.cc")
MARKER = "WEBOS_CHROMIUM_DECODER_DIAGNOSTICS_V1"
METHOD = "void DecoderStream<StreamType>::OnDecoderSelected("
ANCHOR = """  media_log_->SetProperty<StreamTraits::kIsPlatformDecoder>(
      decoder_->IsPlatformDecoder());

  if (is_decrypting_demuxer_stream_selected) {"""
INSERTION = """  // WEBOS_CHROMIUM_DECODER_DIAGNOSTICS_V1
  // Successful selection only: enum names and numeric config, never media data.
  // GetDecoderName() maps a native enum to a fixed Chromium implementation name.
  {
    const auto& diagnostic_config = traits_->GetDecoderConfig(stream_);
    if constexpr (StreamType == DemuxerStream::VIDEO) {
      LOG(INFO) << "CHROMIUM_DECODER v=1 event=selected stream=video"
                << " decoder_id=" << static_cast<int>(decoder_->GetDecoderType())
                << " decoder=\\\"" << GetDecoderName(decoder_->GetDecoderType())
                << "\\\" platform=" << (decoder_->IsPlatformDecoder() ? 1 : 0)
                << " codec_id=" << static_cast<int>(diagnostic_config.codec())
                << " profile_id=" << static_cast<int>(diagnostic_config.profile())
                << " coded_width=" << diagnostic_config.coded_size().width()
                << " coded_height=" << diagnostic_config.coded_size().height();
    } else {
      LOG(INFO) << "CHROMIUM_DECODER v=1 event=selected stream=audio"
                << " decoder_id=" << static_cast<int>(decoder_->GetDecoderType())
                << " decoder=\\\"" << GetDecoderName(decoder_->GetDecoderType())
                << "\\\" platform=" << (decoder_->IsPlatformDecoder() ? 1 : 0)
                << " codec_id=" << static_cast<int>(diagnostic_config.codec())
                << " profile_id=" << static_cast<int>(diagnostic_config.profile())
                << " sample_rate=" << diagnostic_config.samples_per_second()
                << " channels=" << diagnostic_config.channels();
    }
  }

"""
REPLACEMENT = ANCHOR.replace(
    "  if (is_decrypting_demuxer_stream_selected) {",
    INSERTION + "  if (is_decrypting_demuxer_stream_selected) {",
)


class PatchError(ValueError):
    """Source no longer has the reviewed insertion point or exact patch."""


def _validate_clean(text):
    for label, anchor in (
        ("logging include", '#include "base/logging.h"'),
        ("selection method", METHOD),
        ("selection properties", ANCHOR),
    ):
        if text.count(anchor) != 1:
            raise PatchError("%s: expected one %s anchor" % (TARGET, label))
    method_start = text.index(METHOD)
    next_method = text.find("\ntemplate <", method_start)
    insertion_at = text.index(ANCHOR)
    if insertion_at < method_start or (
        next_method != -1 and insertion_at >= next_method
    ):
        raise PatchError("%s: properties moved outside selection method" % TARGET)
    if MARKER in text or "CHROMIUM_DECODER" in text:
        raise PatchError("%s: unexpected existing diagnostic marker" % TARGET)


def patch_text(text):
    """Return exact patched text, or fail without accepting a partial patch."""
    if MARKER in text:
        if text.count(MARKER) != 1 or text.count(REPLACEMENT) != 1:
            raise PatchError("%s: incomplete or modified diagnostic patch" % TARGET)
        _validate_clean(text.replace(REPLACEMENT, ANCHOR, 1))
        return text
    _validate_clean(text)
    return text.replace(ANCHOR, REPLACEMENT, 1)


def configure(source_root, check=False):
    path = Path(source_root) / TARGET
    original = path.read_bytes()
    patched = patch_text(original.decode("utf-8")).encode("utf-8")
    changed = patched != original
    if changed and not check:
        path.write_bytes(patched)
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path("/build/chromium120/src"))
    parser.add_argument("--check", action="store_true", help="validate applicability without writing")
    args = parser.parse_args()
    try:
        changed = configure(args.source_root, check=args.check)
    except (OSError, UnicodeError, PatchError) as error:
        parser.exit(1, "Media diagnostics patch refused: %s\n" % error)
    state = "ready to apply" if args.check and changed else "applied" if changed else "already applied"
    print("CHROMIUM_DECODER selection diagnostics: %s" % state)


if __name__ == "__main__":
    main()
