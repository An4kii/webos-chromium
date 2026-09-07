#!/usr/bin/env python3
"""Exercise the actual pinned SetComposition body with a small controller double.

This host test proves rejection before calling the controller; it is not a
Blink IPC or ARM device test. Supply an unmodified pinned Chromium source root.
"""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile

PREFIX = r'''
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
#include <iostream>
using String = std::string;
template<class T> using Vector = std::vector<T>;
namespace ui { struct ImeTextSpan {}; }
namespace gfx {
struct Range {
  uint32_t a, b;
  bool IsValid() const { return a != UINT32_MAX || b != UINT32_MAX; }
  uint32_t start() const { return a; }
  uint32_t length() const { return a > b ? a - b : b - a; }
};
}
namespace base {
template<class T> T checked_cast(uint32_t value) {
  if (value > static_cast<uint32_t>(std::numeric_limits<T>::max()))
    throw std::range_error("original checked_cast would trap");
  return static_cast<T>(value);
}
}
struct WebRange {
  bool empty = true;
  int begin = 0, end = 0;
  WebRange() = default;
  WebRange(int start, int length) : empty(false), begin(start), end(start + length) {}
};
struct WebInputMethodController {
  int calls = 0;
  bool accepted = true;
  String text = "untouched";
  WebRange range;
  bool SetComposition(const String& value, const Vector<ui::ImeTextSpan>&,
                      WebRange replacement, int, int) {
    ++calls; text = value; range = replacement; return accepted;
  }
};
struct WebFrameWidgetImpl {
  WebInputMethodController* controller;
  WebInputMethodController* GetActiveWebInputMethodController() { return controller; }
  bool SetComposition(const String&, const Vector<ui::ImeTextSpan>&,
                      const gfx::Range&, int, int);
};
'''
SUFFIX = r'''
void require(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}
int main() {
  try {
    WebInputMethodController controller;
    WebFrameWidgetImpl widget{&controller};
    const uint32_t maxInt = std::numeric_limits<int>::max();
    for (const auto range : {gfx::Range{UINT32_MAX, 0}, gfx::Range{0, UINT32_MAX},
                            gfx::Range{maxInt + 1, maxInt + 1},
                            gfx::Range{maxInt, maxInt + 1}}) {
      require(!widget.SetComposition("bad", {}, range, 0, 0), "malformed range accepted");
      require(controller.calls == 0 && controller.text == "untouched", "controller mutated text");
    }
    for (const auto range : {gfx::Range{4, 5}, gfx::Range{7, 10}, gfx::Range{2, 5},
                            gfx::Range{5, 2}, gfx::Range{0, 0},
                            gfx::Range{maxInt, maxInt}, gfx::Range{maxInt - 1, maxInt}}) {
      const int calls = controller.calls;
      require(widget.SetComposition("valid", {}, range, 0, 0), "valid range rejected");
      require(controller.calls == calls + 1, "valid composition not forwarded once");
      require(!controller.range.empty && controller.range.begin == static_cast<int>(range.start()),
              "replacement start changed");
      require(controller.range.end - controller.range.begin == static_cast<int>(range.length()),
              "replacement length changed");
    }
    require(widget.SetComposition("normal", {}, {UINT32_MAX, UINT32_MAX}, 0, 0), "InvalidRange rejected");
    require(controller.range.empty, "InvalidRange lost no-replacement meaning");
    controller.accepted = false;
    require(!widget.SetComposition("valid", {}, {0, 0}, 0, 0), "controller failure not returned");
    widget.controller = nullptr;
    require(!widget.SetComposition("valid", {}, {0, 0}, 0, 0), "null controller not rejected");
  } catch (const std::range_error& error) {
    std::cout << error.what() << '\n';
    return 10;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "actual SetComposition body: all range and forwarding cases passed\n";
}
'''


def method(source):
    begin = source.index('bool WebFrameWidgetImpl::SetComposition(')
    end = source.index('void WebFrameWidgetImpl::CommitText(', begin)
    return source[begin:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('ime_patch', Path(__file__).with_name('configure-ime.py'))
    patch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patch)
    source = (args.source_root / patch.RELATIVE_PATH).read_text()
    if patch.MARKER in source:
        raise RuntimeError('Provide the unmodified pinned source so the failure is reproduced first')
    changed = patch.patch_source(source)
    assert patch.patch_source(changed) == changed
    assert source.replace(patch.ANCHOR, patch.REPLACEMENT).replace(
        '#include <memory>', '#include <limits>\n#include <memory>') == changed
    for broken in (source.replace(patch.ANCHOR, ''), source + patch.ANCHOR,
                   source + '// ' + patch.MARKER):
        try:
            patch.patch_source(broken)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Changed or incomplete patch anchor was accepted')
    compiler = shutil.which('clang++')
    if not compiler:
        raise RuntimeError('clang++ required')
    with tempfile.TemporaryDirectory(prefix='chromium-ime-regression-') as temporary:
        directory = Path(temporary)
        for name, content, expected in (('original', source, 10), ('guarded', changed, 0)):
            cpp = directory / (name + '.cc')
            exe = directory / name
            cpp.write_text(PREFIX + method(content) + SUFFIX)
            subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=undefined', '-fno-sanitize-recover=all',
                            str(cpp), '-o', str(exe)], check=True)
            result = subprocess.run([str(exe)], text=True, capture_output=True)
            print(name + ': ' + result.stdout.strip())
            if result.returncode != expected:
                raise RuntimeError(f'{name}: exit {result.returncode}, expected {expected}: {result.stderr}')
    print('source_sha256=' + hashlib.sha256(source.encode()).hexdigest())
    print('patched_sha256=' + hashlib.sha256(changed.encode()).hexdigest())
    print('Idempotence, changed-anchor refusal and complete-patch checks passed')


if __name__ == '__main__':
    main()
