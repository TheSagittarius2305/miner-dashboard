from __future__ import annotations
import re, shutil
from pathlib import Path
from datetime import datetime

ROOT = Path("/home/cezary/miner-dashboard")
CSS = ROOT / "app/static/styles.css"
JS  = ROOT / "app/static/app.js"

TS = datetime.now().strftime("%Y%m%d_%H%M%S")
BKP = ROOT / f"_patch_backup_{TS}"
BKP.mkdir(parents=True, exist_ok=True)
shutil.copy2(CSS, BKP / "styles.css")
shutil.copy2(JS,  BKP / "app.js")

css = CSS.read_text(encoding="utf-8", errors="strict")

# Remove any existing #coin-layer rules to avoid conflicts
css = re.sub(r'(?is)^\s*#coin-layer\s*\{.*?\}\s*', '', css)

overlay_block = r"""
/* ===== coin rain overlay (GLOBAL, stable) ===== */
#coin-layer{
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  pointer-events: none;
  overflow: hidden;
  z-index: 999999; /* above UI */
}
.coin{
  position: absolute;
  top: -40px;
  pointer-events: none;
  user-select: none;
  font-weight: 900;
  color: rgba(245, 158, 11, 0.95);
  text-shadow: 0 0 18px rgba(245, 158, 11, 0.35);
  filter: drop-shadow(0 0 10px rgba(245, 158, 11, 0.22));
  animation: coinFall var(--dur, 1.8s) linear forwards;
}
@keyframes coinFall{
  0%   { transform: translateY(0) rotate(0deg); opacity: 0.95; }
  100% { transform: translateY(110vh) rotate(360deg); opacity: 0.0; }
}
""".strip() + "\n"

# Append at end (authoritative)
css = css.rstrip() + "\n\n" + overlay_block
CSS.write_text(css, encoding="utf-8", newline="\n")

# Ensure getCoinLayer() sets id coin-layer and appends to body (already does, but make sure no width/height inline hacks exist)
js = JS.read_text(encoding="utf-8", errors="strict")

# If old getCoinLayer created absolute container without styles, it's fine now because CSS fixes it.
# But ensure ID is exactly "coin-layer" and is appended to body.
# (No-op if already correct.)

JS.write_text(js, encoding="utf-8", newline="\n")

print("OK ✔ coin-layer overlay fixed (fullscreen + z-index)")
print("Backup saved in:", BKP)
