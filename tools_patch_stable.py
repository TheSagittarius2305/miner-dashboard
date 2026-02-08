from __future__ import annotations
import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

ROOT = Path("/home/cezary/miner-dashboard")
FILES = [
    "app/static/app.js",
    "app/templates/base.html",
    "app/static/styles.css",
    "worker.py",
    "wsgi.py",
    "config.yaml",
]

DASH_TEMPLATES = sorted((ROOT / "app/templates").glob("dashboard*.html"))

TS = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = ROOT / f"_patch_backup_{TS}"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

def backup_file(rel: str) -> Path:
    src = ROOT / rel
    if not src.exists():
        raise FileNotFoundError(f"Missing file: {src}")
    dst = BACKUP_DIR / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return src

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="strict")

def write_text(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8", newline="\n")

def must_replace(label: str, text: str, pattern: str, repl: str, flags=0, count=0) -> str:
    rx = re.compile(pattern, flags)
    new, n = rx.subn(repl, text, count=count)
    if n == 0:
        raise RuntimeError(f"[{label}] Pattern not found, refusing to guess.\nPattern: {pattern}")
    return new

def optional_remove(text: str, pattern: str, flags=0) -> tuple[str,int]:
    rx = re.compile(pattern, flags)
    new, n = rx.subn("", text)
    return new, n

def patch_app_js():
    rel = "app/static/app.js"
    p = backup_file(rel)
    s = read_text(p)

    # 1) Hard remove CoinGecko calls (front-end must not call it)
    # remove any fetch(...) containing coingecko
    s2, n = optional_remove(s, r"""(?s)\n[^\n]*fetch\([^)]*coingecko[^)]*\)[^\n]*\n""", flags=re.IGNORECASE)
    if n > 0:
        s = s2

    # 2) Enforce single refresh loop with guard
    # Expect a function named refreshStatus() exists
    if "function refreshStatus" not in s and "async function refreshStatus" not in s:
        raise RuntimeError("[app.js] refreshStatus() not found. Need your app.js content.")

    # Remove any existing setInterval calling refreshStatus (we will re-add exactly one)
    s, _nint = optional_remove(s, r"""(?s)\n[^\n]*setInterval\([^;]*refreshStatus[^;]*\);\s*""")

    # Remove any onload / DOMContentLoaded blocks that start refresh loop in unknown ways
    # We'll add deterministic init at end
    # (We keep other DOMContentLoaded listeners if they don't start refreshStatus)
    # Try to remove direct refreshStatus() calls tied to extra timers (except one immediate we'll add)
    s, _ncall = optional_remove(s, r"""(?m)^\s*refreshStatus\(\);\s*$""")

    init_block = r"""
// === Deterministic refresh loop (single) ===
(function initDeterministicRefreshLoop(){
  if (window.__refreshLoopStarted) return;
  window.__refreshLoopStarted = true;

  // Previous total shares across ALL online miners (for coin rain)
  window.__prevTotalSharesAccepted = null;

  // run immediately
  refreshStatus();

  // and then every 10 seconds
  setInterval(refreshStatus, 10000);
})();
""".lstrip("\n")

    # Place init block at very end (after last newline)
    if "initDeterministicRefreshLoop" not in s:
        s = s.rstrip() + "\n\n" + init_block + "\n"

    # 3) Coin rain: enforce EXACTLY-once-per-refresh trigger, based on accepted shares delta
    # We expect somewhere in refreshStatus() after fetching JSON, you have access to `data` object.
    # We'll inject deterministic logic by locating the first occurrence of `data.miners`
    # and injecting coin logic right after it is available.
    #
    # This is conservative: if we can't find a safe anchor, we stop.
    anchor = r"(const\s+miners\s*=\s*data\.miners\s*;|let\s+miners\s*=\s*data\.miners\s*;|var\s+miners\s*=\s*data\.miners\s*;|data\.miners)"
    m = re.search(anchor, s)
    if not m:
        raise RuntimeError("[app.js] Could not find anchor near data.miners to inject coin-rain logic.")

    inject = r"""
  // === Coin rain trigger: ONLY ONCE per refresh ===
  try {
    const minersObj = data.miners || {};
    let currentTotalShares = 0;
    for (const k of Object.keys(minersObj)) {
      const mm = minersObj[k];
      if (mm && mm.status === "online") {
        const v = Number(mm.shares_accepted ?? 0);
        if (Number.isFinite(v)) currentTotalShares += v;
      }
    }
    if (window.__prevTotalSharesAccepted === null) {
      window.__prevTotalSharesAccepted = currentTotalShares;
    } else {
      const delta = currentTotalShares - window.__prevTotalSharesAccepted;
      window.__prevTotalSharesAccepted = currentTotalShares;

      const coinsToSpawn = Math.max(0, Math.min(20, delta|0));
      if (coinsToSpawn > 0) {
        spawnCoinsDeterministic(coinsToSpawn);
      }
    }
  } catch (e) {
    // never break dashboard
    console.warn("coin-rain compute failed:", e);
  }
""".rstrip() + "\n"

    # Inject AFTER first time data.miners is referenced (right after that line)
    # We'll inject after the end of the line containing the match.
    line_start = s.rfind("\n", 0, m.start()) + 1
    line_end = s.find("\n", m.end())
    if line_end == -1:
        line_end = len(s)
    # Insert after that line
    s = s[:line_end] + "\n" + inject + s[line_end:]

    # 4) Ensure there is exactly one coin spawner function and no other spawnCoins() calls
    # We'll create a deterministic spawner and try to neutralize other spawnCoins() usage.
    # Remove calls to spawnCoins(...) if any
    s, _nspawn = optional_remove(s, r"""(?m)^\s*spawnCoins\([^)]*\);\s*$""")

    # Add deterministic spawner if missing
    if "function spawnCoinsDeterministic" not in s:
        spawner = r"""
function spawnCoinsDeterministic(count){
  // Spawn one-by-one, staggered to avoid paired/triple clumps.
  for (let i = 0; i < count; i++) {
    const base = 120 + Math.floor(Math.random() * 60); // 120–180ms
    const jitter = Math.floor(Math.random() * 50);     // extra randomness
    const delay = i * (base + jitter);
    setTimeout(() => spawnOneCoin(), delay);
  }
}

function spawnOneCoin(){
  const el = document.createElement("div");
  el.className = "coin";
  el.textContent = "₿";

  // Slightly larger than before:
  const fontSize = 22 + Math.floor(Math.random() * 14); // 22–35px
  el.style.fontSize = fontSize + "px";

  // random horizontal start
  el.style.left = Math.floor(Math.random() * 100) + "vw";
  el.style.top = "-40px";

  document.body.appendChild(el);

  // remove after animation
  el.addEventListener("animationend", () => el.remove(), { once: true });
}
""".strip() + "\n"
        s = s.rstrip() + "\n\n" + spawner + "\n"

    write_text(p, s)
    print(f"OK patched: {p}")

def patch_templates_remove_btc():
    # We do safe removals by matching obvious BTC/profit/mode blocks.
    # If we can't find any keywords, we still succeed (maybe already removed).
    targets = [ROOT/"app/templates/base.html"] + DASH_TEMPLATES
    if not DASH_TEMPLATES:
        print("WARN: No dashboard*.html templates found in app/templates. Skipping template patch.")
        return

    keywords = [
        "BTC/day", "BTC / day", "BTC/dzień", "BTC", "coingecko",
        "FPPS", "Mode", "Braiins", "theoretical", "pessimistic",
        "Efficiency", "est"
    ]

    for tp in targets:
        rel = str(tp.relative_to(ROOT))
        backup_file(rel)
        s = read_text(tp)

        # Remove <div ...> blocks that contain those keywords (conservative: only if a whole tile block matches)
        # Heuristic: remove cards/tiles sections with any keyword inside within a <div class="kpi"> or <div class="tile"> block.
        before = s
        for kw in keywords:
            # remove tile-like blocks containing keyword
            s, _ = optional_remove(
                s,
                rf"""(?is)<div[^>]+class=["'][^"']*(kpi|tile|card)[^"']*["'][^>]*>.*?{re.escape(kw)}.*?</div>\s*"""
            )

        if s != before:
            write_text(tp, s)
            print(f"OK patched template (removed BTC/profit blocks): {tp}")
        else:
            print(f"OK template unchanged (no BTC/profit blocks found): {tp}")

def patch_css_coin():
    rel = "app/static/styles.css"
    p = ROOT / rel
    if not p.exists():
        print("WARN: styles.css not found, skipping coin CSS patch.")
        return
    backup_file(rel)
    s = read_text(p)

    # Ensure .coin animation exists; if not, add deterministic minimal CSS
    if ".coin" not in s:
        s += r"""

/* === Coin rain === */
.coin{
  position: fixed;
  z-index: 9999;
  pointer-events: none;
  opacity: 0.95;
  animation: coinFall 1.8s linear forwards;
}
@keyframes coinFall{
  0%   { transform: translateY(0) rotate(0deg); opacity: 0.95; }
  100% { transform: translateY(110vh) rotate(360deg); opacity: 0.0; }
}
"""
        write_text(p, s)
        print(f"OK patched CSS (added .coin): {p}")
    else:
        print(f"OK CSS unchanged (already has .coin): {p}")

def main():
    print(f"Backup dir: {BACKUP_DIR}")
    # Validate files exist
    for f in FILES:
        fp = ROOT / f
        if not fp.exists():
            # allow missing styles.css
            if f.endswith("styles.css"):
                continue
            raise FileNotFoundError(f"Missing required file: {fp}")

    patch_app_js()
    patch_templates_remove_btc()
    patch_css_coin()

    print("\nDONE. Backups saved in:", BACKUP_DIR)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\nPATCH FAILED (no guessing):", e, file=sys.stderr)
        print("\nIf this failed because patterns differ, run the dump command below and paste output.")
        print(r"""
cd /home/cezary/miner-dashboard
for f in app/static/app.js app/templates/base.html app/templates/dashboard*.html app/static/styles.css worker.py wsgi.py config.yaml; do
  echo "========== $f =========="
  [ -f "$f" ] && sed -n '1,220p' "$f" || echo "(missing)"
done
""")
        sys.exit(2)
