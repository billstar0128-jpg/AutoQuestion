"""有限、只读的源码防呆检查；只报告位置和类别，不返回匹配内容。"""
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str


def placeholder(value: str) -> bool:
    value = value.strip().strip('\"\'').strip()
    return (not value or value.lower().startswith(('test-', 'mock-', 'fake-', 'example-', 'your-', 'your_', 'placeholder'))
            or (value.startswith('<') and value.endswith('>')) or value in {'...', 'YOUR_API_KEY'})


KEY_PATTERN = re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}')
BEARER_PATTERN = re.compile(r'\bBearer\s+([A-Za-z0-9._~-]{12,})', re.I)
ASSIGNMENT = re.compile(
    r'''["']?(?:LLM_API_KEY|API_KEY|AUTHORIZATION|COOKIE|SESSION_TOKEN|ACCESS_TOKEN)["']?\s*[:=]\s*["']([^"'\r\n]+)["']''', re.I)
ENV_SECRET = re.compile(r'^\s*(?:export\s+)?([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|COOKIE|AUTHORIZATION))\s*=\s*(.*?)\s*$', re.I)


def inspect_text(text: str, name: str, *, example=False) -> list[Finding]:
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        if example and not line.lstrip().startswith('#'):
            match = ENV_SECRET.match(line)
            if match and match[1].upper() not in {'HOTKEY', 'EXIT_KEY'} and not placeholder(match[2]):
                findings.append(Finding(name, number, 'non-placeholder secret in example'))
        values = [(m[0], 'API key pattern') for m in KEY_PATTERN.finditer(line)]
        values += [(m[1], 'Bearer token') for m in BEARER_PATTERN.finditer(line)]
        values += [(m[1], 'credential literal') for m in ASSIGNMENT.finditer(line)]
        for value, kind in values:
            if not placeholder(value) and not placeholder(value.removeprefix('Bearer ')):
                findings.append(Finding(name, number, kind))
    return findings


def scan_project(root: Path) -> list[Finding]:
    # 明确白名单；不遍历 .env、legacy_main.py、profile、日志或虚拟环境。
    paths = [root / name for name in ('main.py', 'README.md', '.env.example', 'requirements.txt', 'requirements-dev.txt')]
    for directory in ('src', 'tests', 'examples'):
        base = root / directory
        if base.is_dir() and not base.is_symlink():
            paths.extend(path for path in base.rglob('*')
                         if path.suffix in {'.py', '.js', '.html', '.json', '.md'}
                         and not any(part.startswith('.') or part == '__pycache__' for part in path.relative_to(base).parts))
    findings = []
    for path in sorted(set(paths)):
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        # 不跟随指向白名单以外的链接，也不读取超大文件。
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            findings.append(Finding(name, 0, 'symlink skipped; manual review required'))
            continue
        try:
            if path.stat().st_size > 1_000_000:
                findings.append(Finding(name, 0, 'file too large for lightweight check'))
                continue
            findings.extend(inspect_text(path.read_text(encoding='utf-8-sig'), name, example=path.name == '.env.example'))
        except (OSError, UnicodeError):
            findings.append(Finding(name, 0, 'file unreadable'))
    return findings
