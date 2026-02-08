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
        raise FileNotFoundError(f"Missing file: {p}")
    dst = BACKUP_DIR / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, dst)
    return p

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="strict")

def write(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8", newline="\n")

def opt_sub(s: str, pattern: str, repl: str = "", flags=0) -> tuple[str,int]:
    rx = re.compile(pattern, flags)
    return rx.subn(repl, s)

def patch_app_js():
    p = backup("app/static/app.js")
    s = read(p)

    # HARD: remove any fetch lines to coingecko/mempool anywhere
    s, n_cg = opt_sub(s, r'(?im)^[^\n]*fetch\([^)]*coingecko[^)]*\)[^\n]*\n', "", flags=0)
    s, n_mp = opt_sub(s, r'(?im)^[^\n]*fetch\([^)]*mempool\.space[^)]*\)[^\n]*\n', "", flags=0)

    # Remove BTC object if present
    s, _ = opt_sub(s, r'(?s)^\s*const\s+BTC\s*=\s*\{.*?\}\s*;\s*\n', "", flags=re.M)

    # Remove known BTC-related functions
    btc_funcs = [
        "setBtcMode", "setActiveBtcModeButtons", "refreshBtcPrice", "refreshDifficulty",
        "btcPerThDayTheoretical", "btcPerThDayByMode", "updateBtcKpis"
    ]
    for fn in btc_funcs:
        s, _ = opt_sub(s, rf'(?s)^\s*async\s+function\s+{fn}\s*\([^)]*\)\s*\{{.*?\n\}}\s*\n', "", flags=re.M)
        s, _ = opt_sub(s, rf'(?s)^\s*function\s+{fn}\s*\([^)]*\)\s*\{{.*?\n\}}\s*\n', "", flags=re.M)

    # Remove any lines referencing BTC UI ids/seg (belt & suspenders)
    s, _ = opt_sub(s, r'(?im)^[^\n]*(btcModeSeg|btcModeLabel|btcModeHint|btcEur|eurFromBtcDay|btcDay|btcMonth|btcPerKwh|kwhDay|totalTH)[^\n]*\n', "", flags=0)

    # Single refresh loop: remove any setInterval(refreshStatus...) anywhere
    s, _ = opt_sub(s, r'(?s)\n[^\n]*setInterval\([^;]*refreshStatus[^;]*\);\s*', "\n", flags=0)
    # remove top-level refreshStatus(); lines
    s, _ = opt_sub(s, r'(?m)^\s*refreshStatus\(\);\s*$', "", flags=0)

    # Find refreshStatus function block
    m_func = re.search(r'(?s)(async\s+function\s+refreshStatus\s*\([^)]*\)\s*\{.*?\n\})', s)
    if not m_func:
        m_func = re.search(r'(?s)(function\s+refreshStatus\s*\([^)]*\)\s*\{.*?\n\})', s)
    if not m_func:
        raise RuntimeError("[app.js] refreshStatus function not found")

    func = m_func.group(1)

    # Find insertion point: after data = await X.json(); OR after any await X.json(); OR after first data.miners usage
    m_json = re.search(r'(?m)^\s*(const|let|var)\s+data\s*=\s*await\s+[a-zA-Z0-9_$.]+\s*\.json\s*\(\s*\)\s*;\s*$', func)
    if not m_json:
        m_json = re.search(r'(?m)^\s*.*await\s+[a-zA-Z0-9_$.]+\s*\.json\s*\(\s*\)\s*;\s*$', func)

    m_anchor = None
    if not m_json:
        m_anchor = re.search(r'(?m)^\s*.*data\.miners.*$', func)

    if not m_json and not m_anchor:
        raise RuntimeError("[app.js] Could not find json parse or data.miners inside refreshStatus to inject coin logic.")

    inject = r"""
  // === Coin rain: ONLY ONCE per refresh (delta of total accepted shares) ===
  try {
    const minersObj = (data && data.miners) ? data.miners : {};
    let currentTotalShares = 0;

    for (const k of Object.keys(minersObj)) {
      const mm = minersObj[k];
      if (mm && mm.status === "online") {
        const v = Number(mm.shares_accepted ?? 0);
        if (Number.isFinite(v)) currentTotalShares += v;
      }
    }

    if (window.__prevTotalSharesAccepted === null || window.__prevTotalSharesAccepted === undefined) {
      window.__prevTotalSharesAccepted = currentTotalShares;
    } else {
      const delta = (currentTotalShares - window.__prevTotalSharesAccepted) | 0;
      window.__prevTotalSharesAccepted = currentTotalShares;

      const coinsToSpawn = Math.max(0, Math.min(20, delta));
      if (coinsToSpawn > 0) spawnCoinsDeterministic(coinsToSpawn);
    }
  } catch(e) {
    console.warn("coin-rain compute failed:", e);
  }
""".rstrip() + "\n"

    if "Coin rain: ONLY ONCE per refresh" not in func:
        if m_json:
            pos = m_json.end()
        else:
            pos = m_anchor.end()
        func2 = func[:pos] + "\n" + inject + func[pos:]
    else:
        func2 = func

    s = s[:m_func.start(1)] + func2 + s[m_func.end(1):]

    # Ensure NO other spawnCoins triggers
    s, _ = opt_sub(s, r'(?m)^\s*spawnCoins\([^)]*\);\s*$', r'// spawnCoins(...) removed (deterministic coin rain)', flags=0)

    # Add deterministic spawner if missing
    if "function spawnCoinsDeterministic" not in s:
        s = s.rstrip() + "\n\n" + r"""
function spawnCoinsDeterministic(count){
  for(let i=0;i<count;i++){
    const base = 120 + Math.floor(Math.random()*60);  // 120–180ms
    const jitter = Math.floor(Math.random()*60);      // extra jitter
    const delay = i * (base + jitter);
    setTimeout(spawnOneCoin, delay);
  }
}

function spawnOneCoin(){
  const el = document.createElement("div");
  el.className = "coin";
  el.textContent = "₿";

  const fontSize = 22 + Math.floor(Math.random()*14); // 22–35px
  el.style.fontSize = fontSize + "px";

  el.style.left = Math.floor(Math.random()*100) + "vw";
  el.style.setProperty("--dur", (1.6 + Math.random()*0.6).toFixed(2) + "s");

  document.body.appendChild(el);
  el.addEventListener("animationend", () => el.remove(), {once:true});
}
""".strip() + "\n"

    # Add single init loop at end (guard)
    if "initDeterministicRefreshLoop" not in s:
        s = s.rstrip() + "\n\n" + r"""
// === Deterministic refresh loop (single) ===
(function initDeterministicRefreshLoop(){
  if (window.__refreshLoopStarted) return;
  window.__refreshLoopStarted = true;

  window.__prevTotalSharesAccepted = null;

  refreshStatus();
  setInterval(refreshStatus, 10000);
})();
""".strip() + "\n"

    write(p, s)
    print(f"OK: {p} (removed coingecko lines: {n_cg}, mempool lines: {n_mp})")

def main():
    print("Backup dir:", BACKUP_DIR)
    patch_app_js()
    print("DONE")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\nPATCH FAILED (no guessing):", e, file=sys.stderr)
        print("\nRun this and paste output (shows where refreshStatus is):")
        print(r"""
cd /home/cezary/miner-dashboard
grep -n "function refreshStatus" -n app/static/app.js || true
grep -n "async function refreshStatus" -n app/static/app.js || true
grep -n "refreshStatus" app/static/app.js | head -n 40
""")
        sys.exit(2)
