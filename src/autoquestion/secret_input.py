"""Secret input never falls back to echoing stdin."""
import getpass
import sys
import warnings

from pydantic import SecretStr
from .config import ConfigError


def masked_input(read_char, write, limit=4096):
    chars = []
    try:
        while True:
            char = read_char()
            if not char or char in ('\x04', '\x1a'):
                raise EOFError()
            if char == '\x03':
                raise KeyboardInterrupt()
            if char in ('\x00', '\xe0'):
                read_char()  # Windows extended key code, not a secret character.
                continue
            if char in ('\r', '\n'):
                return SecretStr(''.join(chars))
            if char in ('\b', '\x7f'):
                if chars:
                    chars.pop()
                    write('\b \b')
            elif char.isprintable():
                if len(chars) >= limit:
                    raise ConfigError('API Key 输入过长；请重新输入。')
                chars.append(char)
                write('*')
    finally:
        chars.clear()
        write('\n')


def read_secret(prompt='API Key (hidden; Ctrl+C cancels): '):
    if sys.platform == 'win32' and sys.stdin.isatty() and sys.stdout.isatty():
        import msvcrt
        print(prompt, end='', flush=True)
        return masked_input(msvcrt.getwch, lambda text: print(text, end='', flush=True))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            return SecretStr(getpass.getpass(prompt))
    except getpass.GetPassWarning:
        raise ConfigError('当前终端无法安全隐藏输入；请在 Windows Terminal 中运行 --setup。') from None
