#!/usr/bin/env python3
"""Offline anchor, fail-closed, and compiled diagnostic-output tests."""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("configure-media-diagnostics.py")
SPEC = importlib.util.spec_from_file_location("media_diagnostics", SCRIPT)
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)

# Small independent excerpt fixture from the pinned source; no media or URLs.
FIXTURE = '''#include "base/logging.h"
template <DemuxerStream::Type StreamType>
void DecoderStream<StreamType>::OnDecoderSelected(
    DecoderStatus::Or<std::unique_ptr<Decoder>> decoder_or_error,
    std::unique_ptr<DecryptingDemuxerStream> decrypting_demuxer_stream) {
  media_log_->SetProperty<StreamTraits::kDecoderName>(
      decoder_->GetDecoderType());
  media_log_->SetProperty<StreamTraits::kIsPlatformDecoder>(
      decoder_->IsPlatformDecoder());

  if (is_decrypting_demuxer_stream_selected) {
    // Original remaining selection logic is not changed by this patch.
  }
}

template <DemuxerStream::Type StreamType>
void DecoderStream<StreamType>::SatisfyRead(ReadResult result) {}
'''


class PatchTests(unittest.TestCase):
    def test_only_inserts_diagnostic_block(self):
        result = PATCH.patch_text(FIXTURE)
        self.assertEqual(result.replace(PATCH.INSERTION, "", 1), FIXTURE)
        self.assertEqual(result.count(PATCH.MARKER), 1)

    def test_idempotent_exact_patch(self):
        result = PATCH.patch_text(FIXTURE)
        self.assertEqual(PATCH.patch_text(result), result)

    def test_missing_duplicate_or_moved_anchor_refused(self):
        for source in (
            FIXTURE.replace("kIsPlatformDecoder", "kChangedProperty"),
            FIXTURE + PATCH.ANCHOR,
            FIXTURE.replace(PATCH.ANCHOR, "") + PATCH.ANCHOR,
            FIXTURE.replace('#include "base/logging.h"', ""),
        ):
            with self.subTest(source=source[:60]):
                with self.assertRaises(PATCH.PatchError):
                    PATCH.patch_text(source)

    def test_partial_modified_or_duplicate_patch_refused(self):
        patched = PATCH.patch_text(FIXTURE)
        for source in (
            FIXTURE + "// " + PATCH.MARKER,
            patched.replace("coded_width=", "unreviewed_field="),
            patched + PATCH.INSERTION,
            patched + '\n// CHROMIUM_DECODER unexpected\n',
        ):
            with self.subTest(source=source[-60:]):
                with self.assertRaises(PATCH.PatchError):
                    PATCH.patch_text(source)

    def test_existing_unowned_marker_refused(self):
        with self.assertRaises(PATCH.PatchError):
            PATCH.patch_text(FIXTURE + '\n// CHROMIUM_DECODER unowned\n')

    def test_check_and_second_apply_do_not_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / PATCH.TARGET
            target.parent.mkdir(parents=True)
            target.write_text(FIXTURE)
            before = target.stat().st_mtime_ns
            self.assertTrue(PATCH.configure(temporary, check=True))
            self.assertEqual(target.read_text(), FIXTURE)
            self.assertEqual(target.stat().st_mtime_ns, before)
            self.assertTrue(PATCH.configure(temporary))
            patched = target.read_bytes()
            modified = target.stat().st_mtime_ns
            self.assertFalse(PATCH.configure(temporary))
            self.assertFalse(PATCH.configure(temporary, check=True))
            self.assertEqual(target.read_bytes(), patched)
            self.assertEqual(target.stat().st_mtime_ns, modified)

    def test_refusal_does_not_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / PATCH.TARGET
            target.parent.mkdir(parents=True)
            original = FIXTURE.replace("kIsPlatformDecoder", "kChangedProperty")
            target.write_text(original)
            with self.assertRaises(PATCH.PatchError):
                PATCH.configure(temporary)
            self.assertEqual(target.read_text(), original)


CPP_FIXTURE = r'''
#include <iostream>
#include <sstream>
#include <string>
#include <type_traits>
struct DemuxerStream { enum Type { AUDIO, VIDEO }; };
enum class VideoDecoderType { kUnknown = 0, kFFmpeg = 2, kVda = 14 };
enum class AudioDecoderType { kFFmpeg = 1 };
std::string GetDecoderName(VideoDecoderType type) {
  switch (type) {
    case VideoDecoderType::kUnknown: return "Unknown Video Decoder";
    case VideoDecoderType::kFFmpeg: return "FFmpegVideoDecoder";
    case VideoDecoderType::kVda: return "VDAVideoDecoder";
  }
  return "";
}
std::string GetDecoderName(AudioDecoderType) { return "FFmpegAudioDecoder"; }
struct Size { int width() const { return 1280; } int height() const { return 720; } };
struct VideoConfig {
  int codec() const { return 1; }
  int profile() const { return 2; }
  Size coded_size() const { return {}; }
  std::string AsHumanReadableString() const { return "PRIVATE_CONFIG_SENTINEL"; }
};
struct AudioConfig {
  int codec() const { return 2; }
  int profile() const { return 0; }
  int samples_per_second() const { return 48000; }
  int channels() const { return 2; }
  std::string AsHumanReadableString() const { return "PRIVATE_CONFIG_SENTINEL"; }
};
template <DemuxerStream::Type Type> struct Traits {
  using Config = std::conditional_t<Type == DemuxerStream::VIDEO, VideoConfig, AudioConfig>;
  using DecoderType = std::conditional_t<Type == DemuxerStream::VIDEO, VideoDecoderType, AudioDecoderType>;
  Config GetDecoderConfig(void*) { return {}; }
};
template <typename Type> struct Decoder {
  Type type;
  bool platform;
  Type GetDecoderType() const { return type; }
  bool IsPlatformDecoder() const { return platform; }
};
struct LogLine {
  std::ostringstream stream;
  ~LogLine() { std::cerr << stream.str() << '\n'; }
};
#define LOG(level) LogLine().stream
template <DemuxerStream::Type StreamType>
void Select(typename Traits<StreamType>::DecoderType type, bool platform) {
  Traits<StreamType> traits;
  auto* traits_ = &traits;
  Decoder<typename Traits<StreamType>::DecoderType> decoder{type, platform};
  auto* decoder_ = &decoder;
  void* stream_ = nullptr;
  /* DIAGNOSTIC_INSERTION */
}
int main() {
  Select<DemuxerStream::VIDEO>(VideoDecoderType::kFFmpeg, false);
  Select<DemuxerStream::AUDIO>(AudioDecoderType::kFFmpeg, false);
  Select<DemuxerStream::VIDEO>(VideoDecoderType::kVda, true);
  Select<DemuxerStream::VIDEO>(VideoDecoderType::kUnknown, false);
}
'''


class CompiledOutputTests(unittest.TestCase):
    def test_audio_video_platform_and_unknown_selection_are_allowlisted(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            self.skipTest("native C++ compiler unavailable; output test not run")
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "diagnostic.cc"
            binary = Path(temporary) / "diagnostic"
            source.write_text(CPP_FIXTURE.replace("/* DIAGNOSTIC_INSERTION */", PATCH.INSERTION))
            compiled = subprocess.run(
                [compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5, check=True)
        self.assertEqual(ran.stdout, "")
        self.assertEqual(ran.stderr.splitlines(), [
            'CHROMIUM_DECODER v=1 event=selected stream=video decoder_id=2 decoder="FFmpegVideoDecoder" platform=0 codec_id=1 profile_id=2 coded_width=1280 coded_height=720',
            'CHROMIUM_DECODER v=1 event=selected stream=audio decoder_id=1 decoder="FFmpegAudioDecoder" platform=0 codec_id=2 profile_id=0 sample_rate=48000 channels=2',
            'CHROMIUM_DECODER v=1 event=selected stream=video decoder_id=14 decoder="VDAVideoDecoder" platform=1 codec_id=1 profile_id=2 coded_width=1280 coded_height=720',
            'CHROMIUM_DECODER v=1 event=selected stream=video decoder_id=0 decoder="Unknown Video Decoder" platform=0 codec_id=1 profile_id=2 coded_width=1280 coded_height=720',
        ])
        self.assertNotIn("PRIVATE_CONFIG_SENTINEL", ran.stderr)


if __name__ == "__main__":
    unittest.main()
