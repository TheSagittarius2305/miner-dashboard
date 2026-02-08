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

def opt_sub(s: str, pattern: str, repl: str = "", flags=0):
    rx = re.compile(pattern, flags)
    return rx.subn(repl, s)

def patch_app_js():
    p = backup("app/static/app.js")
    s = read(p)

    # 0) Hard-remove any fetch to coingecko/mempool (browser MUST NOT call them)
    s, n_cg = opt_sub(s, r'(?im)^[^\n]*fetch\([^)]*coingecko[^)]*\)[^\n]*\n', "")
    s, n_mp = opt_sub(s, r'(?im)^[^\n]*fetch\([^)]*mempool\.space[^)]*\)[^\n]*\n', "")

    # 1) Remove broken DOMContentLoaded init block entirely (we add deterministic one)
    #    This also removes the broken "BTC mode buttons" leftover that caused syntax issues.
    s, n_dom = opt_sub(
        s,
        r'(?s)\n?/\*\s*=====\s*init\s*=====\s*\*/\s*document\.addEventListener\("DOMContentLoaded",\s*\(\)\s*=>\s*\{.*?\n\s*\}\);\s*\n',
        "\n",
        flags=0
    )

    # Also remove any other DOMContentLoaded blocks that call refreshStatus or set intervals (safety)
    s, _ = opt_sub(
        s,
        r'(?s)document\.addEventListener\("DOMContentLoaded",\s*\(\)\s*=>\s*\{.*?refreshStatus\(\).*?\}\);\s*\n',
        "\n"
    )

    # 2) Remove any setInterval that calls refreshStatus (we will add exactly one)
    s, _ = opt_sub(s, r'(?s)\n[^\n]*setInterval\([^;]*refreshStatus[^;]*\);\s*', "\n")

    # 3) Remove stray top-level refreshStatus() calls
    s, _ = opt_sub(s, r'(?m)^\s*refreshStatus\(\);\s*$', "")

    # 4) Find refreshStatus function block
    m_func = re.search(r'(?s)(async\s+function\s+refreshStatus\s*\([^)]*\)\s*\{.*?\n\})', s)
    if not m_func:
        m_func = re.search(r'(?s)(function\s+refreshStatus\s*\([^)]*\)\s*\{.*?\n\})', s)
    if not m_func:
        raise RuntimeError("[app.js] refreshStatus() not found")

    func = m_func.group(1)

    # 5) Ensure there is a `data` variable that points to the parsed JSON
    #    Find: const X = await something.json();
    m_json = re.search(r'(?m)^\s*(const|let|var)\s+([a-zA-Z_]\w*)\s*=\s*await\s+[^;]+?\.json\s*\(\s*\)\s*;\s*$', func)
    if not m_json:
        # sometimes: const j = await (await fetch(...)).json();
        m_json = re.search(r'(?m)^\s*(const|let|var)\s+([a-zA-Z_]\w*)\s*=\s*await\s*\(\s*await\s+fetch\([^;]+?\)\s*\)\.json\s*\(\s*\)\s*;\s*$', func)

    if not m_json:
        raise RuntimeError("[app.js] Could not find a JSON parse line inside refreshStatus() (no 'const x = await ...json();')")

    varname = m_json.group(2)

    # Insert `const data = <varname>;` right after json parse line (unless already exists)
    if re.search(r'(?m)^\s*(const|let|var)\s+data\s*=\s*', func) is None:
        insert_pos = m_json.end()
        alias = f"\n  const data = {varname};\n"
        func = func[:insert_pos] + alias + func[insert_pos:]

    # 6) Ensure coin trigger exists INSIDE refreshStatus, AFTER data is defined, and only once
    coin_block = r"""
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

    # Remove any previous injected coin blocks to prevent duplicates
    func, _ = opt_sub(
        func,
        r'(?s)\n\s*//\s*===\s*Coin rain: ONLY ONCE per refresh.*?\n\s*\}\s*catch\(e\)\s*\{.*?\}\s*\n',
        "\n"
    )

    # Now insert coin block right after `const data = ...;`
    m_data = re.search(r'(?m)^\s*(const|let|var)\s+data\s*=.*?;\s*$', func)
    if not m_data:
        raise RuntimeError("[app.js] data alias not found after insertion (unexpected)")

    pos = m_data.end()
    func = func[:pos] + "\n" + coin_block + func[pos:]

    # Put function back into the full file
    s = s[:m_func.start(1)] + func + s[m_func.end(1):]

    # 7) Deterministic coin spawner (only one)
    # Remove old legacy spawnCoins function if exists (we keep deterministic only)
    s, _ = opt_sub(s, r'(?s)\n\s*/\*\s*=====\s*GLOBAL COIN RAIN\s*=====\s*\*/.*?(?=\n\s*/\*|\Z)', "\n", flags=0)
    s, _ = opt_sub(s, r'(?s)\n\s*function\s+spawnCoins\s*\([^)]*\)\s*\{.*?\n\s*\}\s*\n', "\n")

    if "function spawnCoinsDeterministic" not in s:
        s = s.rstrip() + "\n\n" + r"""
function spawnCoinsDeterministic(count){
  // Spawn one-by-one, staggered, never clumped
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

    # 8) Single refresh loop + UI init (range buttons, compact toggle) with global guard
    init = r"""
// === Deterministic init + refresh loop (single) ===
(function initDeterministic(){
  if (window.__refreshLoopStarted) return;
  window.__refreshLoopStarted = true;

  window.__prevTotalSharesAccepted = null;

  function wireUiOnce(){
    try {
      // auto-compact on mobile first load
      if (window.innerWidth <= 600 && localStorage.getItem("compact") === null) {
        if (window.STATE) window.STATE.compact = true;
      }
      if (typeof applyCompact === "function" && window.STATE) applyCompact();

      if (typeof setActiveRangeButtons === "function") setActiveRangeButtons();

      document.querySelectorAll("#rangeSeg .segbtn").forEach(btn => {
        btn.addEventListener("click", () => {
          if (!window.STATE) return;
          window.STATE.hours = Number(btn.dataset.hours);
          localStorage.setItem("rangeHours", String(window.STATE.hours));
          if (typeof setActiveRangeButtons === "function") setActiveRangeButtons();
        });
      });

      const ct = document.getElementById("compactToggle");
      if (ct) {
        ct.addEventListener("click", () => {
          if (!window.STATE) return;
          window.STATE.compact = !window.STATE.compact;
          if (typeof applyCompact === "function") applyCompact();
        });
      }
    } catch(e) {
      console.warn("UI init failed:", e);
    }
  }

  function start(){
    wireUiOnce();
    refreshStatus();
    setInterval(refreshStatus, 10000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, {once:true});
  } else {
    start();
  }
})();
""".strip() + "\n"

    # Remove older initDeterministicRefreshLoop if exists
    s, _ = opt_sub(s, r'(?s)//\s*===\s*Deterministic refresh loop\s*\(single\)\s*===.*?\)\s*\(\);\s*\n', "\n")
    s, _ = opt_sub(s, r'(?s)\(function\s+initDeterministicRefreshLoop.*?\)\s*\(\);\s*\n', "\n")

    if "function initDeterministic" not in s and "initDeterministic(){" not in s:
        s = s.rstrip() + "\n\n" + init

    write(p, s)
    print(f"OK patched app.js. Backups in: {BACKUP_DIR}")
    print(f"Removed fetch lines: coingecko={n_cg}, mempool={n_mp}, removed DOMContentLoaded blocks={n_dom}")

def patch_css():
    p = backup("app/static/styles.css")
    s = read(p)

    # Ensure coin layer covers whole page and coins are visible above everything
    # Add/replace a clean block (id-based, deterministic)
    block = r"""
/* ===== coin rain (deterministic) ===== */
#coin-layer{
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  pointer-events: none;
  z-index: 99999;
}
.coin{
  position: fixed;
  top: -40px;
  left: 0;
  z-index: 99999;
  pointer-events: none;
  user-select: none;
  font-weight: 900;
  color: rgba(245, 158, 11, 0.95);
  text-shadow: 0 0 18px rgba(245, 158, 11, 0.35);
  filter: drop-shadow(0 0 10px rgba(245, 158, 11, 0.22));
  animation: coinFall var(--dur, 1.8s) linear forwards;
}
@keyframes coinFall{
  0%   { transform: translateY(0) rotate(0deg);   opacity: 0.95; }
  100% { transform: translateY(110vh) rotate(360deg); opacity: 0.0; }
}
""".strip() + "\n"

    # Remove previous messy coin css blocks
    s, _ = opt_sub(s, r'(?s)/\*\s*=====\s*coin rain.*', "", flags=re.I)
    s, _ = opt_sub(s, r'(?s)/\*\s*=====+\s*coin rain.*', "", flags=re.I)
    s, _ = opt_sub(s, r'(?s)/\*\s*===\s*COIN_CSS_START\s*===\s*\*/.*', "", flags=re.I)

    # Append clean block
    s = s.rstrip() + "\n\n" + block
    write(p, s)
    print("OK patched styles.css")

def main():
    print("Backup dir:", BACKUP_DIR)
    patch_app_js()
    patch_css()
    print("DONE")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\nPATCH FAILED:", e, file=sys.stderr)
        sys.exit(2)
