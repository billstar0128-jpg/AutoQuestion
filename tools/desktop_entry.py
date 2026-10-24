"""Windowed executable entry; never installs or launches another Python."""
from pathlib import Path
import sys

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--apply-update':
        from autoquestion.updates import apply_update
        try:
            return apply_update(Path(sys.argv[2]))
        except Exception:
            # Old install/config remain untouched; user can reopen or download manually.
            return 1
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from autoquestion.desktop_self_test import run
        return run(Path(sys.argv[2]))
    if len(sys.argv) == 3 and sys.argv[1] == '--desktop-self-test':
        from autoquestion.desktop_acceptance import run
        return run(Path(sys.argv[2]))
    from autoquestion.desktop_instance import DesktopInstanceError
    try:
        if len(sys.argv) == 3 and sys.argv[1] == '--updated-app':
            from autoquestion.desktop_app import main as updated_desktop
            return updated_desktop(update_receipt=Path(sys.argv[2]))
        from autoquestion.web_ui import main as open_ui
        return open_ui()
    except DesktopInstanceError as error:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('AutoQuestion', str(error), parent=root)
        root.destroy()
        return 1
    except Exception:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('AutoQuestion', '工作台未能启动。请完整解压下载包，保留 _internal 文件夹，并检查 Microsoft Edge WebView2 Runtime。\n官方安装说明：https://developer.microsoft.com/microsoft-edge/webview2/', parent=root)
        root.destroy()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
