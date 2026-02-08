from __future__ import annotations
import re, shutil
from pathlib import Path
from datetime import datetime

JS = Path("/home/cezary/miner-dashboard/app/static/app.js")
TS = datetime.now().strftime("%Y%m%d_%H%M%S")
BKP = JS.parent.parent.parent / f"_patch_backup_{TS}"
BKP.mkdir(parents=True, exist_ok=True)
shutil.copy2(JS, BKP / "app.js")

s = JS.read_text(encoding="utf-8", errors="strict")

# Zamień limit 20 -> brak limitu
old = r'const\s+coins\s*=\s*Math\.max\(0,\s*Math\.min\(20,\s*delta\)\);'
new = r'const coins = Math.max(0, delta);'

if not re.search(old, s):
    raise SystemExit("❌ Nie znaleziono limitu 20 (nic nie zmieniono)")

s = re.sub(old, new, s)

JS.write_text(s, encoding="utf-8", newline="\n")

print("OK ✔ limit 20 USUNIĘTY – coin rain = 1:1 ze shares")
print("Backup zapisany w:", BKP)
