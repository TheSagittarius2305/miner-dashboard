from __future__ import annotations
import re, shutil
from pathlib import Path
from datetime import datetime

P = Path("/home/cezary/miner-dashboard/app/static/app.js")
TS = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = P.parent.parent.parent / f"_patch_backup_{TS}"
BACKUP.mkdir(parents=True, exist_ok=True)
shutil.copy2(P, BACKUP / "app.js")

s = P.read_text(encoding="utf-8", errors="strict")

# 1) USUŃ WSZYSTKIE stare coin-rain blocki (te z `data`)
s = re.sub(
    r'(?s)// === Coin rain: ONLY ONCE per refresh.*?console\.warn\("coin-rain compute failed:", e\);\s*\}',
    '',
    s
)

# 2) WSTRZYKNIJ JEDYNY POPRAWNY coin-rain NA KOŃCU refreshStatus
inject = r'''
  // === Coin rain (STATE.miners only, safe) ===
  try {
    const minersObj = (window.STATE && STATE.miners) ? STATE.miners : {};
    let currentTotalShares = 0;

    for (const k of Object.keys(minersObj)) {
      const m = minersObj[k];
      if (m && m.status === "online") {
        const v = Number(m.shares_accepted ?? 0);
        if (Number.isFinite(v)) currentTotalShares += v;
      }
    }

    if (window.__prevTotalSharesAccepted == null) {
      window.__prevTotalSharesAccepted = currentTotalShares;
    } else {
      const delta = (currentTotalShares - window.__prevTotalSharesAccepted) | 0;
      window.__prevTotalSharesAccepted = currentTotalShares;

      const coins = Math.max(0, Math.min(20, delta));
      if (coins > 0 && typeof spawnCoinsDeterministic === "function") {
        spawnCoinsDeterministic(coins);
      }
    }
  } catch (e) {
    console.warn("coin-rain compute failed:", e);
  }
'''

m = re.search(r'(function\s+refreshStatus\s*\([^)]*\)\s*\{)', s)
if not m:
    raise SystemExit("refreshStatus() not found")

# wstawiamy na sam koniec funkcji refreshStatus
pos = s.rfind('}', m.end())
s = s[:pos] + inject + '\n' + s[pos:]

P.write_text(s, encoding="utf-8", newline="\n")

print("OK ✔ coin-rain fixed (STATE.miners only)")
print("Backup saved in:", BACKUP)
