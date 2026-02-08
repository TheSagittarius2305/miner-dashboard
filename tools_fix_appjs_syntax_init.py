from __future__ import annotations
import re, sys, shutil
from pathlib import Path
from datetime import datetime

P = Path("/home/cezary/miner-dashboard/app/static/app.js")
TS = datetime.now().strftime("%Y%m%d_%H%M%S")
BKP = P.parent.parent.parent / f"_patch_backup_{TS}"
BKP.mkdir(parents=True, exist_ok=True)
shutil.copy2(P, BKP / "app.js")

s = P.read_text(encoding="utf-8", errors="strict")

# Replace the broken init block deterministically:
# from /* ===== init ===== */ up to the line right before /* ===== GLOBAL COIN RAIN ===== */
pat = re.compile(r'(?s)/\*\s*=====\s*init\s*=====\s*\*/\s*document\.addEventListener\("DOMContentLoaded",\s*\(\)\s*=>\s*\{.*?\}\);\s*(?=/\*\s*=====\s*GLOBAL COIN RAIN\s*=====\s*\*/)', re.M)

replacement = r'''/* ===== init (stable) ===== */
document.addEventListener("DOMContentLoaded", () => {
  try {
    if (window.innerWidth <= 600 && localStorage.getItem("compact") === null) {
      STATE.compact = true;
    }
    applyCompact();

    // range buttons
    setActiveRangeButtons();
    document.querySelectorAll("#rangeSeg .segbtn").forEach((btn) => {
      btn.addEventListener("click", () => {
        STATE.hours = Number(btn.dataset.hours);
        localStorage.setItem("rangeHours", String(STATE.hours));
        setActiveRangeButtons();
        // do not start extra loops; refreshStatus loop handles updates
      });
    });

    // compact toggle
    const ct = document.getElementById("compactToggle");
    if (ct) {
      ct.addEventListener("click", () => {
        STATE.compact = !STATE.compact;
        applyCompact();
      });
    }

    // start deterministic refresh loop once
    if (!window.__refreshLoopStarted && typeof refreshStatus === "function") {
      window.__refreshLoopStarted = true;
      window.__prevTotalSharesAccepted = null;
      refreshStatus();
      setInterval(refreshStatus, 10000);
    }
  } catch (e) {
    console.error("init failed:", e);
  }
});
'''

new, n = pat.subn(replacement, s)
if n != 1:
    print("FAILED: init block pattern not found or found multiple times:", n, file=sys.stderr)
    print("Backup saved at:", BKP, file=sys.stderr)
    sys.exit(2)

P.write_text(new, encoding="utf-8", newline="\n")
print("OK fixed app.js init + syntax. Backup:", BKP)
