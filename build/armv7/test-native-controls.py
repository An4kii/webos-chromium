#!/usr/bin/env python3
"""Exercise real patched method bodies with host doubles, then verify anchors.

This does not emulate Blink, Wayland or Mojo. A real ARM build and TV checks are
still required for routing, on-screen keyboard and compositor behavior.
"""
import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile

PREFIX = r'''
#include <iostream>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
namespace blink {
struct WebInputEvent {
  enum class Type {kRawKeyDown, kKeyUp, kChar};
  enum {kControlKey=1, kAltKey=2, kMetaKey=4, kIsAutoRepeat=8};
};
}
namespace ui {
enum {TEXT_INPUT_TYPE_NONE, TEXT_INPUT_TYPE_TEXT, VKEY_RETURN=13};
enum class WidgetState {UNINITIALIZED, SHOW, HIDE, FULLSCREEN, MAXIMIZED,
                        MINIMIZED, RESTORE, ACTIVE, INACTIVE, RESIZE, DESTROYED};
struct KeycodeConverter {
  static std::string DomKeyToKeyString(const std::string& key) {return key;}
};
struct TextState {int type=TEXT_INPUT_TYPE_NONE;};
struct TextInputManager {
  TextState state;
  const TextState* GetTextInputState() {return &state;}
};
}
namespace content {
enum class KeyboardEventProcessingResult {NOT_HANDLED, HANDLED};
struct RenderWidgetHostViewBase {
  bool showing=true; ui::TextInputManager manager;
  bool IsShowing() const {return showing;}
  ui::TextInputManager* GetTextInputManager() {return &manager;}
};
struct WebContents {
  RenderWidgetHostViewBase view; int suspends=0;
  RenderWidgetHostViewBase* GetRenderWidgetHostView() {return &view;}
};
struct NativeWebKeyboardEvent {
  blink::WebInputEvent::Type type;
  std::string dom_key;
  int windows_key_code, modifiers=0;
  auto GetType() const {return type;}
  int GetModifiers() const {return modifiers;}
};
struct MediaSession {
  enum class SuspendType {kUI};
  WebContents* contents;
  static MediaSession* Get(WebContents* contents) {
    static MediaSession instance; instance.contents=contents; return &instance;
  }
  void Suspend(SuspendType) {contents->suspends++;}
};
}
struct Delegate {
  std::vector<std::string> keys;
  void OnKeyEvent(std::string key, int) {keys.push_back(key);}
};
struct AppRuntimeWebContentsDelegate {
  content::KeyboardEventProcessingResult PreHandleKeyboardEvent(
      content::WebContents*, const content::NativeWebKeyboardEvent&) {
    return content::KeyboardEventProcessingResult::NOT_HANDLED;
  }
};
struct PageContents : AppRuntimeWebContentsDelegate {
  bool pointer_key_capture_=false;
  std::set<int> pointer_keys_down_;
  Delegate local_delegate; Delegate* delegate_=&local_delegate;
  std::unique_ptr<content::WebContents> web_contents_=std::make_unique<content::WebContents>();
  content::WebContents* GetWebContents() {return web_contents_.get();}
  void SetPointerKeyCapture(bool);
  content::KeyboardEventProcessingResult PreHandleKeyboardEvent(
      content::WebContents*, const content::NativeWebKeyboardEvent&);
};
struct PageView {
  PageContents contents; bool visible=true; int visibility_calls=0;
  std::vector<PageView*> children;
  auto* GetPageContents() {return &contents;}
  auto GetChildPageViews() {return children;}
  void SetVisible(bool value) {visible=value;visibility_calls++;}
};
struct ShellWindow {
  bool is_closing_=false, page_tree_visible_=true;
  std::unique_ptr<PageView> page_view_=std::make_unique<PageView>();
  void SetPageTreeVisible(bool);
  void WindowHostStateChanged(ui::WidgetState);
};
#define LOG(level) std::cout
void require(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}
'''

SUFFIX = r'''
int main() {
  using Type = blink::WebInputEvent::Type;
  using Result = content::KeyboardEventProcessingResult;
  PageContents page;
  auto key = [&](Type type, std::string name, int code, int modifiers=0) {
    return page.PreHandleKeyboardEvent(page.GetWebContents(), {type,name,code,modifiers});
  };
  require(key(Type::kRawKeyDown,"ArrowRight",39)==Result::NOT_HANDLED, "default captures navigation");
  page.SetPointerKeyCapture(true);
  require(key(Type::kRawKeyDown,"ArrowRight",39)==Result::HANDLED, "pointer arrow not captured");
  require(page.local_delegate.keys==std::vector<std::string>{"ArrowRight"}, "arrow delivered incorrectly");
  key(Type::kKeyUp,"ArrowRight",39);
  key(Type::kRawKeyDown,"ArrowRight",39,blink::WebInputEvent::kIsAutoRepeat);
  require(page.local_delegate.keys.size()==2, "held arrow discarded");
  key(Type::kKeyUp,"ArrowRight",39);
  require(key(Type::kRawKeyDown,"Enter",13)==Result::HANDLED, "click not captured");
  page.web_contents_->view.manager.state.type=ui::TEXT_INPUT_TYPE_TEXT;
  require(key(Type::kChar,"Enter",13)==Result::HANDLED, "click leaked Enter to newly focused input");
  require(key(Type::kRawKeyDown,"Enter",13,blink::WebInputEvent::kIsAutoRepeat)==Result::HANDLED, "held click leaked to input");
  require(page.local_delegate.keys.size()==3, "held Enter clicked repeatedly");
  page.SetPointerKeyCapture(false);
  require(key(Type::kKeyUp,"Enter",13)==Result::HANDLED, "capture-off leaked companion key");
  page.SetPointerKeyCapture(true);
  require(key(Type::kRawKeyDown,"Enter",13)==Result::NOT_HANDLED, "next input Enter consumed");
  require(key(Type::kRawKeyDown,"ArrowLeft",37)==Result::NOT_HANDLED, "caret navigation consumed");
  page.web_contents_->view.manager.state.type=ui::TEXT_INPUT_TYPE_NONE;
  require(key(Type::kRawKeyDown,"BrowserBack",461)==Result::NOT_HANDLED, "Back consumed");
  require(key(Type::kRawKeyDown,"AudioVolumeUp",175)==Result::NOT_HANDLED, "volume consumed");
  require(key(Type::kRawKeyDown,"ArrowLeft",37,blink::WebInputEvent::kControlKey)==Result::NOT_HANDLED, "shortcut consumed");
  page.web_contents_->view.showing=false;
  require(key(Type::kRawKeyDown,"ArrowLeft",37)==Result::NOT_HANDLED, "hidden page captured");
  page.web_contents_->view.showing=true;
  content::WebContents other;
  require(page.PreHandleKeyboardEvent(&other,{Type::kRawKeyDown,"ArrowLeft",37})==Result::NOT_HANDLED, "other page captured");
  require(page.local_delegate.keys.size()==3, "uncaptured keys emitted pointer events");

  ShellWindow window; PageView active, inactive;
  inactive.visible=false;
  window.page_view_->children={&active,&inactive};
  window.WindowHostStateChanged(ui::WidgetState::INACTIVE);
  require(window.page_view_->visible, "focus loss hid app / IME");
  require(active.contents.web_contents_->suspends==0, "focus loss paused media");
  window.WindowHostStateChanged(ui::WidgetState::MINIMIZED);
  require(!window.page_view_->visible && !window.page_tree_visible_, "minimize did not hide app");
  require(active.contents.web_contents_->suspends==1 && inactive.contents.web_contents_->suspends==1, "did not pause all tabs");
  window.WindowHostStateChanged(ui::WidgetState::HIDE);
  require(active.contents.web_contents_->suspends==1, "duplicate hide repeated work");
  window.WindowHostStateChanged(ui::WidgetState::ACTIVE);
  require(!window.page_view_->visible, "activation exposed minimized app");
  window.WindowHostStateChanged(ui::WidgetState::RESTORE);
  require(window.page_view_->visible && active.visible && !inactive.visible, "restore lost selected-tab state");
  require(active.contents.web_contents_->suspends==1, "restore unexpectedly changed media");
  window.is_closing_=true;
  window.WindowHostStateChanged(ui::WidgetState::HIDE);
  require(window.page_view_->visible, "close reentered visibility");
  ShellWindow empty; empty.page_view_.reset();
  empty.WindowHostStateChanged(ui::WidgetState::HIDE);
  require(!empty.page_tree_visible_, "early hide state lost");
  std::cout << "\nNative keyboard and window-state method-body checks passed\n";
}
'''


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    pointer = load('configure-pointer')
    lifecycle = load('configure-window-lifecycle')
    compiler = shutil.which('clang++')
    if not compiler:
        raise RuntimeError('clang++ required')
    with tempfile.TemporaryDirectory(prefix='chromium-native-controls-') as temporary:
        directory = Path(temporary)
        for patch in (pointer, lifecycle):
            for name in patch.patches():
                target = directory / 'src' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(args.source_root / name, target)
            first = patch.apply(directory / 'src')
            assert patch.apply(directory / 'src') == first
            for name, changes in patch.patches().items():
                original = (args.source_root / name).read_text()
                for old, new in changes:
                    assert original.count(old) == 1
                    for broken in (original.replace(old, ''), original + old):
                        try:
                            patch.replace_once(broken, old, new)
                        except RuntimeError:
                            pass
                        else:
                            raise AssertionError('Changed source anchor accepted: ' + name)
        keyboard = pointer.NATIVE_METHODS[pointer.NATIVE_METHODS.index('void PageContents::SetPointerKeyCapture'):]
        cpp = directory / 'native-controls.cc'
        cpp.write_text(PREFIX + keyboard + lifecycle.HELPER + lifecycle.METHODS + SUFFIX)
        exe = directory / 'native-controls'
        subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all', str(cpp), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    print('Pinned-source patch anchors, idempotence and ambiguity refusal passed')


if __name__ == '__main__':
    main()
