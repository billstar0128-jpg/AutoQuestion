"""从源码目录启动；导入不会注册热键。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from autoquestion.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
