from __future__ import annotations
import re
import sys
import shutil
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

def must_sub(label: str, s: str, pattern: str, repl: str, flags=0) -> str:
    rx = re.compile(pattern, flags)
    out, n = rx.subn(repl, s)
    if n == 0:
        raise RuntimeError(f"[{label}] Pattern not found (refusing to guess): {pattern}")
    return out

def opt_sub(s: str, pattern: str, repl: str = "", flags=0) -> tuple[str,int]:
    rx = re.compile(pattern, flags)
    return rx.subn(repl, s)

def patch_base_html():
    p = backup("app/templates/base.html")
    s = read(p)

    # Fix accidental double query params (not required, but deterministic cleanup)
    s, _ = opt_sub(s, r'(<script\s+src="/static/app\.js\?v=[^"]+)\?v=\d+("></script>)', r"\1\2", flags=re.I)

    write(p, s)
    print("OK:", p)

def patch_dashboard_templates():
    # dashboard.html has meta refresh: remove it (full reload breaks single loop)
    if (ROOT/"app/templates/dashboard.html").exists():
        p = backup("app/templates/dashboard.html")
        s = read(p)
        s, _ = opt_sub(s, r'(?im)^\s*<meta\s+http-equiv="refresh"[^>]*>\s*$', "", flags=0)
        write(p, s)
        print("OK:", p)

    # dashboard_pro.html: keep ONLY 3 KPI boxes
    p = backup("app/templates/dashboard_pro.html")
    s = read(p)

    # Remove meta refresh if exists
    s, _ = opt_sub(s, r'(?im)^\s*<meta\s+http-equiv="refresh"[^>]*>\s*$', "", flags=0)

    # Replace whole KPI block with 3 boxes only
    new_kpi = r'''
<div class="kpi mb-3">
  <div class="box">
    <div class="lbl">⚡ Łączny pobór</div>
    <div class="val"><span id="totalW">--</span> W</div>
  </div>

  <div class="box">
    <div class="lbl">💸 Koszt / dzień ({{ "%.2f"|format(price) }} €/kWh)</div>
    <div class="val"><span id="eurDay">--</span> €</div>
  </div>

  <div class="box">
    <div class="lbl">📆 Koszt / miesiąc</div>
    <div class="val"><span id="eurMonth">--</span> €</div>
  </div>
</div>
'''.strip("\n")

    s = must_sub(
        "dashboard_pro.html KPI",
        s,
        r'(?s)<div\s+class="kpi\s+mb-3">\s*.*?\s*</div>\s*\n\s*\n<div\s+class="cardx\s+p-3">',
        new_kpi + "\n\n<div class=\"cardx p-3\">",
        flags=0
    )

    write(p, s)
    print("OK:", p)

def patch_styles_css():
    p = backup("app/static/styles.css")
    s = read(p)

    # Replace ALL coin-related CSS with a clean deterministic block.
    # We delete from "/* ===== coin rain" OR "/* === COIN_CSS_START === */" to end, then append clean block.
    s, n1 = opt_sub(s, r'(?s)/\*\s*=====\s*coin rain.*$', "", flags=re.I)
    s, n2 = opt_sub(s, r'(?s)/\*\s*===\s*COIN_CSS_START\s*===\s*\*/.*$', "", flags=re.I)

    clean = r"""

/* ===== coin rain (deterministic) ===== */
.coin{
  position: fixed;
  z-index: 9999;
  pointer-events: none;
  user-select: none;
  font-weight: 900;
  color: rgba(245, 158, 11, 0.95);
  text-shadow: 0 0 18px rgba(245, 158, 11, 0.35);
  filter: drop-shadow(0 0 10px rgba(245, 158, 11, 0.22));
  top: -40px;
  left: 0;
  animation: coinFall var(--dur, 1.8s) linear forwards;
}
@keyframes coinFall{
  0%   { transform: translateY(0) rotate(0deg);   opacity: 0.95; }
  100% { transform: translateY(110vh) rotate(360deg); opacity: 0.0; }
}
""".rstrip() + "\n"

    if clean.strip() not in s:
        s = s.rstrip() + "\n" + clean

    write(p, s)
    print("OK:", p)

def patch_app_js():
    p = backup("app/static/app.js")
    s = read(p)

    # 1) Remove BTC estimation block completely (from comment to UI state marker)
    # Your file has: /* ===== BTC estimation ===== ... */ then /* ===== UI state ===== */
    s, n = opt_sub(
        s,
        r'(?s)/\*\s*=====\s*BTC estimation\s*=====\s*\*/.*?/\*\s*=====\s*UI state\s*=====\s*\*/',
        '/* ===== UI state ===== */',
        flags=re.I
    )

    # 2) Remove any remaining coingecko/mempool fetch lines (safety)
    s, _ = opt_sub(s, r'(?is)^[^\n]*fetch\([^)]*coingecko[^)]*\)[^\n]*\n', "", flags=0)
    s, _ = opt_sub(s, r'(?is)^[^\n]*fetch\([^)]*mempool\.space[^)]*\)[^\n]*\n', "", flags=0)

    # 3) Kill any existing meta refresh logic (none in JS)
    # 4) Ensure exactly ONE refresh loop:
    #    - Remove any setInterval that calls refreshStatus
    s, _ = opt_sub(s, r'(?s)\n[^\n]*setInterval\([^;]*refreshStatus[^;]*\);\s*', "\n", flags=0)

    #    - Remove stray direct refreshStatus() calls at top-level (we'll add our own)
    s, _ = opt_sub(s, r'(?m)^\s*refreshStatus\(\);\s*$', "", flags=0)

    # 5) Inject coin delta logic INSIDE refreshStatus() right after JSON parse.
    # Find: "const data = await r.json();" or similar
    # We refuse to guess if refreshStatus isn't present.
    if "refreshStatus" not in s:
        raise RuntimeError("[app.js] refreshStatus not found")

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

    # Insert after first occurrence of "await r.json()" within refreshStatus.
    # We'll locate refreshStatus block and then locate await .json line inside it.
    m_func = re.search(r'(?s)(async\s+function\s+refreshStatus\s*\([^)]*\)\s*\{.*?\n\})', s)
    if not m_func:
        m_func = re.search(r'(?s)(function\s+refreshStatus\s*\([^)]*\)\s*\{.*?\n\})', s)
    if not m_func:
        raise RuntimeError("[app.js] refreshStatus function block not found (unexpected structure)")

    func_block = m_func.group(1)
    m_json = re.search(r'(?m)^\s*(const|let|var)\s+data\s*=\s*await\s+[a-zA-Z0-9_$.]+\.\s*json\s*\(\s*\)\s*;\s*$', func_block)
    if not m_json:
        # slightly more permissive: await r.json() without const data =
        m_json = re.search(r'(?m)^\s*([a-zA-Z0-9_$.]+\s*=\s*)?await\s+[a-zA-Z0-9_$.]+\.json\s*\(\s*\)\s*;\s*$', func_block)
    if not m_json:
        raise RuntimeError("[app.js] Could not find 'data = await r.json()' inside refreshStatus to inject coin logic.")

    insert_pos = m_json.end()
    func_block2 = func_block[:insert_pos] + "\n" + inject + func_block[insert_pos:]

    s = s[:m_func.start(1)] + func_block2 + s[m_func.end(1):]

    # 6) Make sure there are ZERO other spawn triggers (remove spawnCoins(...) calls if present)
    s, _ = opt_sub(s, r'(?m)^\s*spawnCoins\([^)]*\);\s*$', r'// spawnCoins(...) removed (deterministic coin rain)', flags=0)

    # 7) Add deterministic coin spawner (fixed + stagger + bigger range)
    if "function spawnCoinsDeterministic" not in s:
        s = s.rstrip() + "\n\n" + r"""
function spawnCoinsDeterministic(count){
  // Spawn one-by-one (no clumps)
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

  // slightly larger than before:
  const fontSize = 22 + Math.floor(Math.random()*14); // 22–35px
  el.style.fontSize = fontSize + "px";

  el.style.left = Math.floor(Math.random()*100) + "vw";
  el.style.setProperty("--dur", (1.6 + Math.random()*0.6).toFixed(2) + "s");

  document.body.appendChild(el);
  el.addEventListener("animationend", () => el.remove(), {once:true});
}
""".strip() + "\n"

    # 8) Add SINGLE refresh loop init with guard at end
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
    print("OK:", p)

def main():
    print("Backup dir:", BACKUP_DIR)

    # Patch files
    patch_base_html()
    patch_dashboard_templates()
    patch_styles_css()
    patch_app_js()

    print("\nDONE. Backups saved in:", BACKUP_DIR)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\nPATCH FAILED (no guessing):", e, file=sys.stderr)
        sys.exit(2)
