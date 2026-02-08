from __future__ import annotations
import re, sys, shutil
from pathlib import Path
from datetime import datetime

ROOT = Path("/home/cezary/miner-dashboard")
TS = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = ROOT / f"_patch_backup_{TS}"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

def backup(rel: str) -> Path:
    p = ROOT / rel
    if not p.exists():
        raise FileNotFoundError(p)
    dst = BACKUP_DIR / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, dst)
    return p

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="strict")

def write(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8", newline="\n")

def main():
    p = backup("app/static/app.js")
    s = read(p)

    # remove any remaining calls / references that could crash after BTC removal
    # We only remove LINES (safe & deterministic).
    patterns = [
        r'(?im)^[^\n]*updateBtcKpis\s*\([^)]*\)\s*;[^\n]*\n',
        r'(?im)^[^\n]*refreshBtcPrice\s*\([^)]*\)\s*;[^\n]*\n',
        r'(?im)^[^\n]*refreshDifficulty\s*\([^)]*\)\s*;[^\n]*\n',
        r'(?im)^[^\n]*setActiveBtcModeButtons\s*\([^)]*\)\s*;[^\n]*\n',
        r'(?im)^[^\n]*setBtcMode\s*\([^)]*\)\s*;[^\n]*\n',
        r'(?im)^[^\n]*(btcModeSeg|btcModeLabel|btcModeHint|btcEur|eurFromBtcDay|btcDay|btcMonth|btcPerKwh|kwhDay|totalTH)[^\n]*\n',
    ]

    removed = 0
    for pat in patterns:
        s2, n = re.subn(pat, "", s)
        if n:
            removed += n
            s = s2

    # final safety: ensure refreshStatus has its own try/catch wrapper around whole body
    # (only if not already)
    if "function refreshStatus" in s or "async function refreshStatus" in s:
        # best-effort: we don't rewrite function structure here.
        pass

    write(p, s)
    print("Backup dir:", BACKUP_DIR)
    print("OK hotfix applied, lines removed:", removed)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FAILED:", e, file=sys.stderr)
        sys.exit(2)
