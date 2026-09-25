"""Local candidate audit. No network, real .env reads, or credential access."""
import argparse
from fnmatch import fnmatch
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from autoquestion import __version__
from autoquestion.secret_safety import Finding, inspect_text

ROOT_FILES = {'main.py', 'README.md', 'SECURITY.md', 'PRIVACY.md', 'CONTRIBUTING.md',
              'CHANGELOG.md', 'requirements.txt', 'requirements-dev.txt', 'pyproject.toml',
              '.gitignore', '.gitattributes', '.editorconfig', '.env.example', 'LICENSE', 'NOTICE'}
DIRECTORIES = {'src', 'tests', 'examples', 'docs', '.github', 'tools'}
SUFFIXES = {'.py', '.js', '.html', '.md', '.txt', '.toml', '.yml', '.yaml'}
IGNORED_DIRS = {'.git', '__pycache__', '.pytest_cache', '.venv', 'venv', '.idea', '.vscode',
                'logs', 'screenshots', 'captures', 'build', 'dist', 'htmlcov', '.cache',
                'AppData', 'user-data', 'browser-profile', '.local-browsers', 'ms-playwright', '.playwright'}
IGNORED_FILES = {'legacy_main.py', '.coverage', 'coverage.xml', 'config.json'}
IGNORE_RULES = {'.env', '.env.*', '!.env.example', '.venv/', '.venv-*/', '__pycache__/',
                '*.py[cod]', '.pytest_cache/', '.coverage', 'htmlcov/', 'logs/', 'screenshots/',
                'build/', 'dist/', 'legacy_main.py', 'config.json', 'credentials*.json', '.local-browsers/'}
REQUIRED = (ROOT_FILES - {'LICENSE', 'NOTICE'}) | {
    'docs/ARCHITECTURE.md', 'docs/DEVELOPMENT.md', 'docs/CONFIGURATION.md',
    'docs/SECURITY_MODEL.md', 'docs/RELEASE_CHECKLIST.md', 'docs/MANUAL_ACCEPTANCE_M13.md',
    f'docs/RELEASE_NOTES_{__version__}.md', '.github/workflows/ci.yml',
    '.github/ISSUE_TEMPLATE/bug_report.md', '.github/ISSUE_TEMPLATE/feature_request.md',
    '.github/pull_request_template.md', 'examples/demo_quiz.html', 'examples/demo_canvas_quiz.html',
    'src/autoquestion/capture/dom_extract.js'}


def excluded(path):
    parts = path.parts
    if any(p in IGNORED_DIRS or p.startswith('.venv-') or p.endswith('.egg-info') for p in parts):
        return True
    name = path.name
    return (name in IGNORED_FILES or ((name == '.env' or name.startswith('.env.')) and name != '.env.example')
            or any(fnmatch(name, pattern) for pattern in ('*.pyc', '*.pyo', '*.log', '*.tmp',
                   '*.cred', '*.key', 'credentials*.json', '.coverage.*', '*.zip', '*.whl', '*.tar.gz',
                   'capture-*.png', '*.capture.png', '*.tmp.png')))


def candidate_files(root=ROOT):
    """List names first; never follow symlinks/junctions or open unknown/private files."""
    result, issues = [], []
    def visit(directory):
        for path in sorted(directory.iterdir()):
            relative = path.relative_to(root)
            if excluded(relative):
                continue
            # Windows junctions also cross the audited directory boundary.
            if (path.is_symlink() or getattr(path, 'is_junction', lambda: False)()
                    or not path.resolve().is_relative_to(root.resolve())):
                issues.append(Finding(relative.as_posix(), 0, 'link requires manual review'))
            elif path.is_dir():
                if len(relative.parts) == 1 and path.name not in DIRECTORIES:
                    issues.append(Finding(relative.as_posix(), 0, 'unexpected directory; contents not read'))
                else:
                    visit(path)
            elif (len(relative.parts) == 1 and path.name in ROOT_FILES) or (
                    len(relative.parts) > 1 and path.suffix.lower() in SUFFIXES):
                result.append(path)
            else:
                issues.append(Finding(relative.as_posix(), 0, 'unexpected candidate/binary; contents not read'))
    visit(root)
    return result, issues


def inspect_candidate(path, root):
    name = path.relative_to(root).as_posix()
    if path.stat().st_size > 1_000_000:
        return [Finding(name, 0, 'oversized candidate')]
    try:
        raw = path.read_bytes()
        text = raw.decode('utf-8')
    except (OSError, UnicodeError):
        return [Finding(name, 0, 'not readable UTF-8')]
    issues = inspect_text(text, name, example=path.name == '.env.example')
    if raw.startswith(b'\xef\xbb\xbf') or '\ufffd' in text:
        issues.append(Finding(name, 0, 'encoding marker requires review'))
    if re.search(r'data:image/[a-z+]+;base64,[A-Za-z0-9+/=]{80,}', text):
        issues.append(Finding(name, 0, 'embedded image requires review'))
    if re.search(r'[A-Z]:[\\/]Users[\\/](?!Public\b|example\b)[^\s\\/]+', text, re.I):
        issues.append(Finding(name, 0, 'personal absolute path'))
    if path.suffix == '.md':
        for target in re.findall(r'\]\(([^\s)]+)\)', text):
            if target.startswith(('https://', 'http://', '#', 'mailto:')):
                continue
            local = (path.parent / target.split('#')[0]).resolve()
            if not local.is_relative_to(root.resolve()) or not local.exists():
                issues.append(Finding(name, 0, 'broken or out-of-project local link'))
    return issues


def audit(root=ROOT):
    files, issues = candidate_files(root)
    present = {p.relative_to(root).as_posix() for p in files}
    issues.extend(Finding(name, 0, 'required public file missing') for name in sorted(REQUIRED - present))
    for path in files:
        issues.extend(inspect_candidate(path, root))
    ignore = root / '.gitignore'
    if ignore.exists():
        rules = set(ignore.read_text(encoding='utf-8').splitlines())
        if not IGNORE_RULES <= rules:
            issues.append(Finding('.gitignore', 0, 'required exclusions missing'))
    return files, issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='Print reviewed candidate paths, never file contents')
    args = parser.parse_args()
    files, issues = audit()
    for item in issues:
        print(f'FAIL {item.path}:{item.line}: {item.kind}; content redacted')
    if args.list:
        for path in files:
            print(path.relative_to(ROOT).as_posix())
    print(f'Candidate audit: {"FAIL" if issues else "PASS"}; {len(files)} files; {len(issues)} findings')
    print('Limited static audit, not a guarantee about all secrets or Git history.')
    if not (ROOT / 'LICENSE').exists():
        print('PUBLICATION BLOCKER: LICENSE has not been selected.')
    return bool(issues)


if __name__ == '__main__':
    raise SystemExit(main())
