#!/usr/bin/env python3
"""Expose bounded native pointer routing to the trusted browser shell UI.

The default remains normal keyboard navigation. Opt-in interception belongs to
one PageContents; it never reads devices or injects system-wide TV input.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

NATIVE_METHODS = r'''
// WEBOS_CHROMIUM_REMOTE_POINTER: coordinates are view-local DIPs. Route via
// Chromium's hit tester so out-of-process frames receive real mouse input.
void PageContents::DispatchPointerEvent(int type, int x, int y, int delta_y) {
  if (!web_contents_ || !pointer_key_capture_ || type < 0 || type > 2)
    return;
  auto* view = static_cast<content::RenderWidgetHostViewBase*>(
      web_contents_->GetRenderWidgetHostView());
  if (!view || !view->IsShowing())
    return;
  const gfx::Rect bounds = view->GetViewBounds();
  if (x < 0 || y < 0 || x >= bounds.width() || y >= bounds.height() ||
      delta_y < -720 || delta_y > 720)
    return;
  auto* host = view->host();
  auto* router = host && host->delegate()
                     ? host->delegate()->GetInputEventRouter() : nullptr;
  if (!router)
    return;
  const gfx::PointF local(x, y);
  const gfx::PointF screen(bounds.x() + x, bounds.y() + y);
  const auto now = base::TimeTicks::Now();
  if (type == 2) {
    if (delta_y == 0)
      return;
    blink::WebMouseWheelEvent wheel(blink::WebInputEvent::Type::kMouseWheel,
                                    blink::WebInputEvent::kNoModifiers, now);
    wheel.SetPositionInWidget(local);
    wheel.SetPositionInScreen(screen);
    wheel.delta_units = ui::ScrollGranularity::kScrollByPrecisePixel;
    wheel.delta_y = -delta_y;
    wheel.event_action = blink::WebMouseWheelEvent::EventAction::kScrollVertical;
    wheel.phase = blink::WebMouseWheelEvent::kPhaseBegan;
    router->RouteMouseWheelEvent(view, &wheel, ui::LatencyInfo());
    wheel.delta_y = 0;
    wheel.phase = blink::WebMouseWheelEvent::kPhaseEnded;
    router->RouteMouseWheelEvent(view, &wheel, ui::LatencyInfo());
    return;
  }
  blink::WebMouseEvent move(blink::WebInputEvent::Type::kMouseMove,
                            local, screen, blink::WebMouseEvent::Button::kNoButton,
                            0, blink::WebInputEvent::kNoModifiers, now);
  router->RouteMouseEvent(view, &move, ui::LatencyInfo());
  if (type == 1) {
    blink::WebMouseEvent down(blink::WebInputEvent::Type::kMouseDown,
                              local, screen, blink::WebMouseEvent::Button::kLeft,
                              1, blink::WebInputEvent::kLeftButtonDown, now);
    blink::WebMouseEvent up(blink::WebInputEvent::Type::kMouseUp,
                            local, screen, blink::WebMouseEvent::Button::kLeft,
                            1, blink::WebInputEvent::kNoModifiers, now);
    router->RouteMouseEvent(view, &down, ui::LatencyInfo());
    router->RouteMouseEvent(view, &up, ui::LatencyInfo());
  }
}

void PageContents::SetPointerKeyCapture(bool capture) {
  pointer_key_capture_ = capture;
}

content::KeyboardEventProcessingResult PageContents::PreHandleKeyboardEvent(
    content::WebContents* source, const content::NativeWebKeyboardEvent& event) {
  const auto unhandled = [&]() {
    return AppRuntimeWebContentsDelegate::PreHandleKeyboardEvent(source, event);
  };
  const bool down = event.GetType() == blink::WebInputEvent::Type::kRawKeyDown;
  const int code = event.windows_key_code;
  // Clicking a text field can change IME state before this key's Char/KeyUp
  // arrives. Finish a captured key sequence before consulting the new focus.
  if (!down && pointer_keys_down_.count(code)) {
    if (event.GetType() == blink::WebInputEvent::Type::kKeyUp)
      pointer_keys_down_.erase(code);
    return content::KeyboardEventProcessingResult::HANDLED;
  }
  if (down && code == ui::VKEY_RETURN && pointer_keys_down_.count(code) &&
      (event.GetModifiers() & blink::WebInputEvent::kIsAutoRepeat))
    return content::KeyboardEventProcessingResult::HANDLED;
  if (down)
    pointer_keys_down_.erase(code);
  if (!pointer_key_capture_ || !delegate_ || !web_contents_ ||
      source != web_contents_.get() ||
      (event.GetModifiers() & (blink::WebInputEvent::kControlKey |
                               blink::WebInputEvent::kAltKey |
                               blink::WebInputEvent::kMetaKey)))
    return unhandled();
  auto* view = static_cast<content::RenderWidgetHostViewBase*>(
      web_contents_->GetRenderWidgetHostView());
  if (!view || !view->IsShowing())
    return unhandled();
  // Preserve editing and the TV IME when a mouse click focuses a text field,
  // including a field inside a child frame.
  auto* manager = view->GetTextInputManager();
  const auto* text = manager ? manager->GetTextInputState() : nullptr;
  if (text && text->type != ui::TEXT_INPUT_TYPE_NONE)
    return unhandled();
  const std::string key = ui::KeycodeConverter::DomKeyToKeyString(event.dom_key);
  const bool enter = key == "Enter" || event.windows_key_code == ui::VKEY_RETURN;
  if (!enter && key != "ArrowLeft" && key != "ArrowRight" &&
      key != "ArrowUp" && key != "ArrowDown")
    return unhandled();
  if (down) {
    pointer_keys_down_.insert(code);
    if (!(enter && (event.GetModifiers() & blink::WebInputEvent::kIsAutoRepeat)))
      delegate_->OnKeyEvent(enter ? "Enter" : key, code);
  }
  // Consume key-up/character companions too; never move the page and cursor
  // with the same physical key, or activate an element a second time on Enter.
  return content::KeyboardEventProcessingResult::HANDLED;
}

'''


def replace_once(source, old, new):
    if source.count(new) == 1:
        return source
    if source.count(old) != 1:
        raise RuntimeError('Native pointer source anchor differs: ' + old[:90])
    return source.replace(old, new, 1)


def patches():
    app = 'neva/app_runtime/app/app_runtime_page_contents'
    service = 'neva/browser_shell/service/browser_shell_page_contents_impl'
    injection = 'neva/injection/renderer/browser_shell/browser_shell_page_contents'
    return {
        app + '.h': [
            ('  void SetFocus();', '  void SetFocus();\n  void DispatchPointerEvent(int type, int x, int y, int delta_y);\n  void SetPointerKeyCapture(bool capture);'),
            ('  // WebContentsDelegate\n', '  // WebContentsDelegate\n  content::KeyboardEventProcessingResult PreHandleKeyboardEvent(\n      content::WebContents* source,\n      const content::NativeWebKeyboardEvent& event) override;\n'),
            ('  std::set<uint32_t> key_codes_filter_;', '  std::set<uint32_t> key_codes_filter_;\n  bool pointer_key_capture_ = false;\n  std::set<int> pointer_keys_down_;'),
        ],
        app + '.cc': [
            ('#include "content/browser/renderer_host/render_widget_host_view_base.h"',
             '#include "content/browser/renderer_host/render_widget_host_view_base.h"\n'
             '#include "content/browser/renderer_host/render_widget_host_delegate.h"\n'
             '#include "content/browser/renderer_host/render_widget_host_impl.h"\n'
             '#include "content/browser/renderer_host/render_widget_host_input_event_router.h"\n'
             '#include "content/browser/renderer_host/text_input_manager.h"\n'
             '#include "content/public/common/input/native_web_keyboard_event.h"\n'
             '#include "third_party/blink/public/common/input/web_mouse_event.h"\n'
             '#include "third_party/blink/public/common/input/web_mouse_wheel_event.h"\n'
             '#include "ui/base/ime/mojom/text_input_state.mojom.h"\n'
             '#include "ui/events/keycodes/keyboard_codes.h"\n'
             '#include "ui/latency/latency_info.h"'),
            ('void PageContents::SetAcceptedLanguages(std::string languages) {', NATIVE_METHODS + 'void PageContents::SetAcceptedLanguages(std::string languages) {'),
        ],
        'neva/browser_shell/service/public/mojom/browser_shell_page_contents.mojom': [
            ('  SetFocus();', '  SetFocus();\n  DispatchPointerEvent(int32 type, int32 x, int32 y, int32 delta_y);\n  SetPointerKeyCapture(bool capture);'),
        ],
        service + '.h': [
            ('  void SetFocus() override;', '  void SetFocus() override;\n  void DispatchPointerEvent(int32_t type, int32_t x, int32_t y,\n                            int32_t delta_y) override;\n  void SetPointerKeyCapture(bool capture) override;'),
        ],
        service + '.cc': [
            ('void PageContentsImpl::SetAcceptedLanguages(const std::string& languages) {',
             'void PageContentsImpl::DispatchPointerEvent(int32_t type, int32_t x,\n'
             '                                              int32_t y, int32_t delta_y) {\n'
             '  if (page_contents_)\n'
             '    page_contents_->DispatchPointerEvent(type, x, y, delta_y);\n}\n\n'
             'void PageContentsImpl::SetPointerKeyCapture(bool capture) {\n'
             '  if (page_contents_)\n'
             '    page_contents_->SetPointerKeyCapture(capture);\n}\n\n'
             'void PageContentsImpl::SetAcceptedLanguages(const std::string& languages) {'),
        ],
        injection + '.h': [
            ('  void SetFocus();', '  void SetFocus();\n  void DispatchPointerEvent(int type, int x, int y, int delta_y);\n  void SetPointerKeyCapture(bool capture);'),
        ],
        injection + '.cc': [
            ('void BrowserShellPageContents::EnableHandShapedCursorForLinks() {',
             'void BrowserShellPageContents::DispatchPointerEvent(int type, int x,\n'
             '                                                     int y, int delta_y) {\n'
             '  if (remote_.is_bound())\n'
             '    remote_->DispatchPointerEvent(type, x, y, delta_y);\n}\n\n'
             'void BrowserShellPageContents::SetPointerKeyCapture(bool capture) {\n'
             '  if (remote_.is_bound())\n'
             '    remote_->SetPointerKeyCapture(capture);\n}\n\n'
             'void BrowserShellPageContents::EnableHandShapedCursorForLinks() {'),
            ('      .SetMethod(kSetFocusMethodName, &BrowserShellPageContents::SetFocus)',
             '      .SetMethod(kSetFocusMethodName, &BrowserShellPageContents::SetFocus)\n'
             '      .SetMethod("dispatchPointerEvent",\n'
             '                 &BrowserShellPageContents::DispatchPointerEvent)\n'
             '      .SetMethod("setPointerKeyCapture",\n'
             '                 &BrowserShellPageContents::SetPointerKeyCapture)'),
        ],
    }


def apply(root):
    pending = []
    for name, changes in patches().items():
        path = root / name
        before = path.read_text()
        after = before
        for old, new in changes:
            after = replace_once(after, old, new)
        pending.append((path, before, after))
    result = []
    for path, before, after in pending:
        if before != after:
            path.write_text(after)
        result.append({'path': path.relative_to(root).as_posix(),
                       'sha256': hashlib.sha256(after.encode()).hexdigest()})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path,
                        default=Path(os.environ.get('WEBOS_CHROMIUM_SRC', '/build/chromium120/src')))
    args = parser.parse_args()
    print(json.dumps({'native_pointer_sources': apply(args.source_root)}, indent=2))


if __name__ == '__main__':
    main()
