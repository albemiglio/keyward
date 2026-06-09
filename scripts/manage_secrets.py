#!/usr/bin/env python3
"""
key-vault — secret slot management (cross-platform helper).

Usage:
    manage_secrets.py list
    manage_secrets.py remove <name>

Called by the /key-list and /key-rm slash commands. Replaces bash-based
implementations so the plugin works identically on macOS, Linux, and Windows.

NEVER prints secret values.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

SECRETS_DIR = Path.home() / ".claude" / "secrets"


def cmd_list() -> int:
    if not SECRETS_DIR.is_dir():
        print("no secrets saved yet (vault directory does not exist)")
        return 0
    entries = sorted(
        p for p in SECRETS_DIR.iterdir()
        if p.is_file() and p.suffix == ".txt" and not p.name.startswith(".")
    )
    if not entries:
        print("no secrets saved yet")
        return 0
    print(f"{len(entries)} secret slot(s) in {SECRETS_DIR}:\n")
    for p in entries:
        try:
            stat = p.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            size = stat.st_size
            mode = oct(stat.st_mode & 0o777)
            print(f"  {p.stem:30s}  {size:>5d}b  {mode}  modified {mtime}")
        except OSError as exc:
            print(f"  {p.stem:30s}  <stat failed: {exc}>")
    print("\nUse /key-rm <name> to delete a slot.")
    return 0


def secure_overwrite(path: Path) -> None:
    """Best-effort: overwrite with zeros before unlink. Not guaranteed on SSDs
    with wear-leveling or COW filesystems (APFS, Btrfs), but doesn't hurt."""
    try:
        size = path.stat().st_size
        with path.open("r+b") as f:
            f.seek(0)
            f.write(b"\x00" * size)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
    except OSError:
        pass


def cmd_remove(name: str) -> int:
    if not name:
        print("usage: /key-rm <name>", file=sys.stderr)
        return 2
    # Strip any path components for safety.
    safe = Path(name).name
    target = SECRETS_DIR / f"{safe}.txt"
    if not target.is_file():
        print(f"no slot named '{safe}'")
        return 1
    secure_overwrite(target)
    try:
        target.unlink()
    except OSError as exc:
        print(f"failed to delete '{safe}': {exc}", file=sys.stderr)
        return 1
    print(f"deleted: {safe}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: manage_secrets.py {list|remove <name>}", file=sys.stderr)
        return 2
    sub = sys.argv[1]
    if sub == "list":
        return cmd_list()
    if sub == "remove":
        name = sys.argv[2] if len(sys.argv) >= 3 else ""
        return cmd_remove(name)
    print(f"unknown subcommand: {sub}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
