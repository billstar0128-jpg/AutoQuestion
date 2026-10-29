"""Small non-secret display preferences; independent of model configuration and WebView cache."""
import json
import os
from pathlib import Path
import tempfile


def _validated(data):
    if (type(data) is not dict or set(data) != {'theme'} or type(data['theme']) is not str
            or data['theme'] not in {'system', 'light', 'dark'}):
        raise ValueError('界面主题无效。')
    return {'theme': data['theme']}


def _unique(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError('重复字段。')
        data[key] = value
    return data


class UIPreferences:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            if self.path.stat().st_size > 4096:
                return {'theme': 'system'}
            return _validated(json.loads(self.path.read_text(encoding='utf-8'), object_pairs_hook=_unique))
        except (OSError, ValueError, UnicodeError):
            return {'theme': 'system'}

    def save(self, data):
        data = _validated(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', prefix='.ui-preferences-', suffix='.tmp',
                                             dir=self.path.parent, delete=False) as output:
                temporary = Path(output.name)
                json.dump(data, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return data
