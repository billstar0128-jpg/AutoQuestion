"""标准库 CLI；诊断入口不依赖业务模块或第三方依赖导入成功。"""
import argparse
from pathlib import Path
import sys

from . import __version__


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="AutoQuestion：AUTO / Vision / DOM / 离线 Demo")
    parser.add_argument('--env-file', type=Path, help='显式加载本地配置；Doctor 不读取此文件')
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument('--doctor', action='store_true', help='只检查本地环境，不启动热键或模型请求')
    commands.add_argument('--version', action='store_true', help='显示版本')
    commands.add_argument('--setup', action='store_true', help='重新运行设置向导，保存后直接启动')
    commands.add_argument('--show-config', action='store_true', help='显示配置，不读取或显示凭据值')
    commands.add_argument('--reset-config', action='store_true', help='确认后删除用户配置；凭据删除单独确认')
    commands.add_argument('--open-demo', action='store_true', help='仅本次打开受管理 Demo；不修改输入模式')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.version:
        print(f'AutoQuestion {__version__}')
        return 0
    if args.doctor:
        from .doctor import run_doctor
        return run_doctor(env_file_requested=args.env_file is not None)
    try:
        from .app import main as run
        from .config import ConfigError
        from .credentials import CredentialError
        from .setup_wizard import SetupCancelled
        from .startup import resolve_startup, show_config, reset_config
    except ImportError:
        print('运行依赖缺失或无法导入；请运行 --doctor，并使用 .venv-win 安装 requirements.txt。', file=sys.stderr)
        return 1
    try:
        if args.show_config:
            return show_config(args)
        if args.reset_config:
            return reset_config()
        runtime = resolve_startup(args)
        return run(parsed_args=args, runtime=runtime)
    except (SetupCancelled, KeyboardInterrupt, EOFError):
        print('Setup / configuration action cancelled; AutoQuestion 未启动。')
        return 0
    except (ConfigError, CredentialError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        print('配置或启动失败；未输出可能包含 Secret 的异常。请运行 --doctor 或 --setup。', file=sys.stderr)
        return 1
