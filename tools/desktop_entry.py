"""Windowed executable entry; never installs or launches another Python."""
from pathlib import Path
import sys

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from autoquestion.desktop_self_test import run
        return run(Path(sys.argv[2]))
    try:
        from autoquestion.web_ui import main as open_ui
        return open_ui()
    except Exception:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('AutoQuestion', '工作台未能启动。请完整解压下载包，保留 _internal 文件夹，再双击 AutoQuestion.exe。', parent=root)
        root.destroy()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
