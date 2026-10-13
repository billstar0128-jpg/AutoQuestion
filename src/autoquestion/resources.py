"""Resolve bundled read-only assets without depending on the working directory."""
from pathlib import Path
import sys


def resource_root():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]
