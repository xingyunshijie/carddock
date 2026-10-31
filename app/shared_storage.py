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
        if entry.is_dir():
            roots.append(entry.resolve())
    return roots


def container_path(value, mapping, allowed):
    path = Path(value)
    if '..' in path.parts:
        raise ValueError('路径中不能包含 ..')
    choices = []
    for target, host in mapping.items():
        try:
            relative = path.relative_to(Path(host))
        except ValueError:
            continue
        candidate = Path(target) / relative
        if any(candidate == root or root in candidate.parents for root in allowed):
            choices.append((len(Path(host).parts), str(candidate)))
    return max(choices, key=lambda p: p[0])[1] if choices else value


def host_path(value, mapping):
    path = Path(value)
    choices = []
    for target, host in mapping.items():
        try:
            relative = path.relative_to(Path(target))
        except ValueError:
            continue
        choices.append((len(Path(target).parts), str(Path(host) / relative)))
    return max(choices, key=lambda p: p[0])[1] if choices else value
