"""Double-click launcher with a graphical one-time dependency bootstrap."""
import os
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parent


def launch():
    window_python = ROOT / '.venv-win/Scripts/pythonw.exe'
    python = ROOT / '.venv-win/Scripts/python.exe'
    quiet = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    if window_python.exists() and Path(sys.prefix).resolve() != (ROOT / '.venv-win').resolve():
        subprocess.Popen([str(window_python), str(Path(__file__).resolve())], cwd=ROOT, creationflags=quiet)
        return
    dependencies = subprocess.run([str(python), '-c', 'import pydantic,openai,playwright,PIL,dotenv,websockets'],
                                  cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  creationflags=quiet).returncode if python.exists() else 1
    if dependencies:
        import tkinter as tk
        from tkinter import messagebox, ttk
        dialog = tk.Tk()
        dialog.withdraw()
        if not messagebox.askyesno('AutoQuestion · 初次准备',
                                  '首次使用需要创建项目 Python 环境并从网络安装依赖。\n\n点击“是”自动准备，完成后打开工作台。不会安装浏览器或读取你的 API Key。', parent=dialog):
            dialog.destroy()
            return
        dialog.deiconify()
        dialog.title('AutoQuestion · 正在准备')
        dialog.geometry('420x150')
        dialog.resizable(False, False)
        label = ttk.Label(dialog, text='正在创建环境、安装依赖，请稍候…', padding=20)
        label.pack()
        progress = ttk.Progressbar(dialog, mode='indeterminate', length=350)
        progress.pack(pady=5)
        progress.start()
        completed = threading.Event()
        result = []
        def install():
            try:
                if not python.exists():
                    subprocess.run([sys.executable, '-m', 'venv', str(ROOT / '.venv-win')], cwd=ROOT,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=quiet, check=True, timeout=120)
                subprocess.run([str(python), '-m', 'pip', '--isolated', 'install', '--no-cache-dir', '-r', str(ROOT / 'requirements.txt')],
                               cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=quiet, check=True, timeout=900,
                               env=dict(os.environ, PIP_CONFIG_FILE=os.devnull))
                result.append(True)
            except (OSError, subprocess.SubprocessError):
                result.append(False)
            finally:
                completed.set()
        worker = threading.Thread(target=install, daemon=False)
        worker.start()
        dialog.protocol('WM_DELETE_WINDOW', lambda: messagebox.showinfo('AutoQuestion', '请等待本次安装结束后关闭。', parent=dialog))
        def check():
            if not completed.is_set():
                dialog.after(200, check)
                return
            if not result[0]:
                messagebox.showerror('AutoQuestion', '准备失败。请检查网络、Python 安装及项目目录权限，然后重新双击重试。\n详细安装步骤见 README。', parent=dialog)
            dialog.destroy()
        dialog.after(200, check)
        dialog.mainloop()
        worker.join()
        if not result[0]:
            return
        subprocess.Popen([str(window_python), str(Path(__file__).resolve())], cwd=ROOT, creationflags=quiet)
        return
    sys.path.insert(0, str(ROOT / 'src'))
    from autoquestion.web_ui import main
    main()


if __name__ == '__main__':
    try:
        launch()
    except Exception:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('AutoQuestion', '工作台未能启动。请检查 Python 和本机环境，再重新打开。\n未显示可能包含密钥的异常信息。', parent=root)
        root.destroy()
