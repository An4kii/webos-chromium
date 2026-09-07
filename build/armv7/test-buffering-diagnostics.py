#!/usr/bin/env python3
"""Compile the actual patched buffering method against observable client doubles."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile

PREFIX = r'''
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <vector>
enum BufferingState { BUFFERING_HAVE_NOTHING, BUFFERING_HAVE_ENOUGH };
enum BufferingStateChangeReason {
  BUFFERING_CHANGE_REASON_UNKNOWN, DEMUXER_UNDERFLOW, DECODER_UNDERFLOW
};
enum class MediaLogEvent { kBufferingStateChanged };
enum class SerializableBufferingStateType { kVideo };
template<SerializableBufferingStateType> struct SerializableBufferingState {
  BufferingState state; BufferingStateChangeReason reason;
};
struct MediaLog {
  BufferingState last_state; BufferingStateChangeReason last_reason;
  template<MediaLogEvent, class T> void AddEvent(T value) {
    last_state = value.state; last_reason = value.reason;
  }
};
struct Client {
  int calls = 0; BufferingState last_state; BufferingStateChangeReason last_reason;
  void OnBufferingStateChange(BufferingState state, BufferingStateChangeReason reason) {
    ++calls; last_state = state; last_reason = reason;
  }
};
struct TaskRunner { bool RunsTasksInCurrentSequence() { return true; } };
struct Decoder { bool pending; bool is_demuxer_read_pending() { return pending; } };
struct LogLine { std::ostringstream out; ~LogLine() { std::cout << out.str() << '\n'; } };
#define LOG(level) LogLine().out
#define DCHECK(value) do { if (!(value)) throw std::runtime_error("DCHECK"); } while (false)
struct VideoRendererImpl {
  enum State { kPlaying, kFlushing };
  State state_; TaskRunner* task_runner_; Decoder* video_decoder_stream_;
  MediaLog* media_log_; Client* client_; int player_id_ = 17;
  void OnBufferingStateChange(BufferingState buffering_state);
};
'''
SUFFIX = r'''
int main() {
  TaskRunner task; Decoder decoder{false}; MediaLog log; Client client;
  VideoRendererImpl renderer{VideoRendererImpl::kPlaying, &task, &decoder, &log, &client};
  const BufferingState states[] = {BUFFERING_HAVE_NOTHING, BUFFERING_HAVE_NOTHING,
                                  BUFFERING_HAVE_ENOUGH, BUFFERING_HAVE_NOTHING};
  const BufferingStateChangeReason reasons[] = {DECODER_UNDERFLOW, DEMUXER_UNDERFLOW,
                  BUFFERING_CHANGE_REASON_UNKNOWN, BUFFERING_CHANGE_REASON_UNKNOWN};
  for (int index = 0; index < 4; ++index) {
    decoder.pending = index == 1;
    if (index == 3) renderer.state_ = VideoRendererImpl::kFlushing;
    renderer.OnBufferingStateChange(states[index]);
    if (client.calls != index + 1 || client.last_state != states[index] ||
        client.last_reason != reasons[index] || log.last_state != states[index] ||
        log.last_reason != reasons[index]) return 1;
  }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('buffer_patch', Path(__file__).with_name('configure-buffering-diagnostics.py'))
    patch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patch)
    source = (args.source_root / patch.TARGET).read_text()
    after = patch.patch_text(source)
    assert patch.patch_text(after) == after
    assert after.replace(patch.INSERTION, '').replace('#include "base/logging.h"\n', '') == source
    for broken in (source.replace(patch.ANCHOR, ''), source + patch.ANCHOR,
                   source + '// ' + patch.MARKER):
        try:
            patch.patch_text(broken)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Invalid patch anchor accepted')
    begin = after.index('void VideoRendererImpl::OnBufferingStateChange(')
    end = after.index('void VideoRendererImpl::OnWaiting(', begin)
    with tempfile.TemporaryDirectory(prefix='chromium-buffering-test-') as temporary:
        cpp = Path(temporary) / 'buffering.cc'
        binary = Path(temporary) / 'buffering'
        cpp.write_text(PREFIX + after[begin:end] + SUFFIX)
        subprocess.run([shutil.which('clang++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        str(cpp), '-o', str(binary)], check=True)
        output = subprocess.check_output([str(binary)], text=True)
    expected = [
        'CHROMIUM_BUFFERING v=1 stream=video player_id=17 state=0 reason_id=2 reason=decoder_underflow playing=1',
        'CHROMIUM_BUFFERING v=1 stream=video player_id=17 state=0 reason_id=1 reason=demuxer_underflow playing=1',
        'CHROMIUM_BUFFERING v=1 stream=video player_id=17 state=1 reason_id=0 reason=unknown playing=1',
        'CHROMIUM_BUFFERING v=1 stream=video player_id=17 state=0 reason_id=0 reason=unknown playing=0',
    ]
    assert output.splitlines() == expected, output
    print(output, end='')
    print('Actual method: classification, client forwarding, fixed fields and patch integrity passed')


if __name__ == '__main__':
    main()
