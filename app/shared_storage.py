"""Discover shared folders granted by the NAS installation, without host-root access."""
import os
from pathlib import Path


def shared_roots(directory):
    if not directory:
        return []
    parent = Path(directory)
    if parent.is_symlink() or not parent.is_dir():
        return []
    roots = []
    for entry in sorted(parent.iterdir(), key=lambda p: p.name.casefold()):
        if entry.name.startswith(('.', '@')) or entry.is_symlink():
            continue
        if entry.is_dir() and os.access(entry, os.R_OK | os.X_OK):
            roots.append(entry.resolve())
    return roots
