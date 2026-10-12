"""Export a static interactive preview. Never includes local config or secrets."""
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from autoquestion.provider_presets import public_presets


def build(destination=None):
    destination = ROOT / 'dist' if destination is None else Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('index.html', 'app.js', 'style.css'):
        shutil.copyfile(ROOT / 'src/autoquestion/web' / name, destination / name)
    (destination / 'providers.json').write_text(json.dumps({'providers': public_presets(), 'checked': '2026-10-13'}, ensure_ascii=False, indent=2), encoding='utf-8')
    return destination


if __name__ == '__main__':
    print('Static UI preview:', build())
