#!/usr/bin/env python3
"""Connect the browser shell's webOS window state to its WebView tree.

Window focus is deliberately independent: the TV keyboard and system overlays
can take focus without hiding the browser. Only real hide/minimize events pause
media and hide the main WebView; child-tab visibility is retained on restore.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

HELPER = r'''
// WEBOS_CHROMIUM_WINDOW_LIFECYCLE: pause every tab when the TV hides this app.
// The user explicitly resumes playback on return; merely raising the browser
// must not start old media in a background tab.
void PausePageTree(PageView* view) {
  if (!view)
    return;
  auto* contents = view->GetPageContents();
  if (contents && contents->GetWebContents()) {
    content::MediaSession::Get(contents->GetWebContents())
        ->Suspend(content::MediaSession::SuspendType::kUI);
  }
  for (auto* child : view->GetChildPageViews())
    PausePageTree(child);
}
'''

METHODS = r'''void ShellWindow::SetPageTreeVisible(bool visible) {
  if (is_closing_ || page_tree_visible_ == visible)
    return;
  page_tree_visible_ = visible;
  if (!page_view_)
    return;
  if (!visible)
    PausePageTree(page_view_.get());
  // NativeViewHost hides the Aura window; WebContentsViewAura then updates
  // page visibility. The children retain their own selected-tab visibility.
  page_view_->SetVisible(visible);
  LOG(INFO) << "CHROMIUM_WINDOW visible=" << visible;
}

void ShellWindow::WindowHostStateChanged(ui::WidgetState new_state) {
  switch (new_state) {
    case ui::WidgetState::HIDE:
    case ui::WidgetState::MINIMIZED:
      SetPageTreeVisible(false);
      break;
    case ui::WidgetState::SHOW:
    case ui::WidgetState::RESTORE:
    case ui::WidgetState::FULLSCREEN:
    case ui::WidgetState::MAXIMIZED:
      SetPageTreeVisible(true);
      break;
    default:
      // ACTIVE/INACTIVE and keyboard focus are not visibility events.
      break;
  }
}'''


def replace_once(source, old, new):
    if source.count(new) == 1:
        return source
    if source.count(old) != 1:
        raise RuntimeError('Window lifecycle source anchor differs: ' + old[:90])
    return source.replace(old, new, 1)


def patches():
    base = 'neva/app_runtime/app/app_runtime_shell_window'
    return {
        base + '.h': [
            ('  void Init(const CreateParams& params);',
             '  void Init(const CreateParams& params);\n  void SetPageTreeVisible(bool visible);'),
            ('  bool is_closing_ = false;',
             '  bool is_closing_ = false;\n  bool page_tree_visible_ = true;'),
        ],
        base + '.cc': [
            ('#include "neva/app_runtime/app/app_runtime_page_view.h"',
             '#include "base/logging.h"\n'
             '#include "content/public/browser/media_session.h"\n'
             '#include "neva/app_runtime/app/app_runtime_page_contents.h"\n'
             '#include "neva/app_runtime/app/app_runtime_page_view.h"'),
            ('const int kKeyboardHeightMargin = 10;',
             'const int kKeyboardHeightMargin = 10;\n' + HELPER),
            ('  page_view_->SetParentShellWindow(this);',
             '  page_view_->SetParentShellWindow(this);\n'
             '  page_view_->SetVisible(page_tree_visible_);'),
            ('void ShellWindow::WindowHostStateChanged(ui::WidgetState new_state) {}', METHODS),
            ('void ShellWindow::WindowHostStateAboutToChange(ui::WidgetState state) {}',
             'void ShellWindow::WindowHostStateAboutToChange(ui::WidgetState state) {\n'
             '  if (state == ui::WidgetState::HIDE || state == ui::WidgetState::MINIMIZED)\n'
             '    SetPageTreeVisible(false);\n}'),
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
    print(json.dumps({'window_lifecycle_sources': apply(args.source_root)}, indent=2))


if __name__ == '__main__':
    main()
