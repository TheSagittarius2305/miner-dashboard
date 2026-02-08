
// ===== coin rain anti-dup (by shares value) =====
window.__coinRainLastSpawn = window.__coinRainLastSpawn || {};


// ===== coin rain global lock (prevent double spawn) =====
window.__coinRainLock = window.__coinRainLock || {};


function setById(id, val){
  const el = document.getElementById(id);
  if(!el) return;
  el.textContent = (val === null || val === undefined || val === "") ? "--" : String(val);
}

/* ===== helpers ===== */
function fmt(n, d=1){
  if(n === null || n === undefined) return "--";
  const x = Number(n);
  if(Number.isNaN(x)) return "--";
  return x.toFixed(d);
}
function fmtInt(n){
  if(n === null || n === undefined) return "--";
  const x = Number(n);
  if(Number.isNaN(x)) return "--";
  return x.toLocaleString("en-US");
}
function fmtShort(n){
  if(n === null || n === undefined) return "--";
  const x = Number(n);
  if(Number.isNaN(x)) return "--";
  if(x >= 1e12) return (x/1e12).toFixed(2).replace(/\.00$/, "") + "T";
  if(x >= 1e9)  return (x/1e9 ).toFixed(2).replace(/\.00$/, "") + "B";
  if(x >= 1e6)  return (x/1e6 ).toFixed(1).replace(/\.0$/,  "") + "M";
  if(x >= 1e3)  return (x/1e3 ).toFixed(0) + "K";
  return x.toString();
}
function bestMeta(n){
  const x = Number(n);
  if(Number.isNaN(x)) return {cls:"", emo:""};
  if(x >= 1e12) return {cls:"bestT", emo:"🏆"};
  if(x >= 1e9)  return {cls:"bestB", emo:"🥇"};
  if(x >= 1e6)  return {cls:"bestM", emo:"🥈"};
  if(x >= 1e3)  return {cls:"bestK", emo:"🥉"};
  return {cls:"", emo:""};
}
function fmtUptime(sec){
  if(sec === null || sec === undefined) return "--";
  sec = Number(sec);
  if(Number.isNaN(sec)) return "--";
  const h = Math.floor(sec/3600);
  const m = Math.floor((sec%3600)/60);
  const s = Math.floor(sec%60);
  return `${h}h ${m}m ${s}s`;
}
function setText(id, val){
  const el = document.getElementById(id);
  if(el) el.textContent = val;
}
function clamp01(x){
  x = Number(x);
  if(Number.isNaN(x)) return 0;
  return Math.max(0, Math.min(1, x));
}
function niceRange(vals){
  const arr = vals.filter(v => v !== null && v !== undefined && !Number.isNaN(Number(v))).map(Number);
  if(arr.length < 2) return {min: 0, max: 1};
  let mn = Math.min(...arr);
  let mx = Math.max(...arr);
  if(mn === mx){
    mn = mn * 0.98;
    mx = mx * 1.02;
    if(mn === mx){ mn -= 0.1; mx += 0.1; }
  }
  const pad = (mx - mn) * 0.18;
  return {min: mn - pad, max: mx + pad};
}

/* ===== BTC estimation =====
theoretical BTC/day per TH/s derived from difficulty:
network_hashrate = difficulty * 2^32 / 600  (H/s)
btc_per_day = (miner_hashrate / network_hashrate) * 144 * block_reward

=> btc_per_day_per_TH = (1e12 * 86400 * block_reward) / (difficulty * 2^32)
*/
/* ===== UI state ===== */
const STATE = {
  hours: Number(localStorage.getItem("rangeHours") || 24),
  compact: (localStorage.getItem("compact") || "0") === "1",
  charts: {},
  prevShares: {}
};

function applyCompact(){
  document.body.classList.toggle("compact", STATE.compact);
  localStorage.setItem("compact", STATE.compact ? "1" : "0");
}

function setActiveRangeButtons(){
  document.querySelectorAll(".segbtn").forEach(b => {
    if(!b.dataset.hours) return;
    const h = Number(b.dataset.hours);
    b.classList.toggle("active", h === STATE.hours);
  });
  if(window.MINERS){
    window.MINERS.forEach(id => setText(id+"-rangeLbl", `${STATE.hours}h`));
  }
}

/* ===== status dot ===== */
function setDot(id, status, asicTemp){
  const dot = document.getElementById(id + "-dot");
  const st  = document.getElementById(id + "-status");
  if(!dot || !st) return;

  st.textContent = status || "--";
  dot.classList.remove("dot-good","dot-warn","dot-bad");

  if(status !== "online"){
    dot.classList.add("dot-bad");
    return;
  }
  const t = Number(asicTemp);
  if(!Number.isNaN(t) && t >= 75) dot.classList.add("dot-warn");
  else dot.classList.add("dot-good");
}

/* ===== progress bars ===== */
function setBar(id, pct01, warn=false){
  const el = document.getElementById(id);
  if(!el) return;
  el.style.width = `${Math.round(clamp01(pct01)*100)}%`;
  el.classList.toggle("warn", !!warn);
}

/* ===== history ===== */
async function loadHistory(minerId, hours){
  const r = await fetch(`/api/history/${minerId}?hours=${hours}`, {cache:"no-store"});
  return await r.json();
}

/* ===== charts ===== */
function makeChart(minerId, series, labels, status){
  const canvas = document.getElementById(`${minerId}-spark`);
  if(!canvas) return null;

  const color = status === "online" ? "rgba(34,211,238,0.95)" : "rgba(239,68,68,0.95)";
  const bg = status === "online" ? "rgba(34,211,238,0.12)" : "rgba(239,68,68,0.10)";
  const {min, max} = niceRange(series);

  return new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "TH/s",
        data: series,
        borderColor: color,
        backgroundColor: bg,
        fill: true,
        borderWidth: 2.5,
        pointRadius: 0,
        tension: 0.35
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: true,
          displayColors: false,
          callbacks: {
            title: (items) => items?.[0]?.label ? ` ${items[0].label}` : "",
            label: (ctx) => ` ${fmt(ctx.parsed.y, 2)} TH/s`
          }
        }
      },
      scales: {
        x: { display: false },
        y: {
          display: true,
          min,
          max,
          ticks: {
            color: "rgba(255,255,255,0.55)",
            maxTicksLimit: 4,
            callback: (v) => `${Number(v).toFixed(2)}`
          },
          grid: { color: "rgba(255,255,255,0.08)" }
        }
      }
    }
  });
}

async function refreshChart(minerId, status){
  const data = await loadHistory(minerId, STATE.hours);

  const pts = data
    .map(p => p.hashrate)
    .filter(v => v !== null && v !== undefined)
    .map(Number)
    .filter(v => !Number.isNaN(v));

  if(pts.length === 0) return;

  const maxN = 140;
  let series = pts;
  if(series.length > maxN){
    const step = Math.ceil(series.length / maxN);
    series = series.filter((_, i) => i % step === 0);
  }

  let labels = data.map(p => p.time);
  if(labels.length > series.length){
    const step = Math.ceil(labels.length / series.length);
    labels = labels.filter((_, i) => i % step === 0).slice(0, series.length);
  } else if(labels.length < series.length){
    labels = series.map((_, i) => String(i));
  }

  if(STATE.charts[minerId]){
    try{ STATE.charts[minerId].destroy(); }catch(e){}
    delete STATE.charts[minerId];
  }
  STATE.charts[minerId] = makeChart(minerId, series, labels, status);
}

/* ===== main refresh ===== */
async function refreshStatus(){
  const r = await fetch("/api/status", {cache:"no-store"});
  const j = await r.json();


  

  const data = j;


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

  setText("now", j.now || "--:--:--");
  setText("totalW", fmt(j.total_w, 1));
  setText("eurDay", fmt(j.eur_day, 2));
  setText("eurMonth", fmt(j.eur_month, 2));

  // refresh external data (price + difficulty)

  const miners = j.miners || {};

  function calcMaxW(id, w){
    if(String(id).toLowerCase().includes("nerd")) return Math.max(110, (w||0)*1.25 + 10);
    return Math.max(60, (w||0)*1.25 + 10);
  }

  // total TH for BTC KPI

  for(const id in miners){
    const m = miners[id];

    setDot(id, m.status, m.asic_temp);
    setText(id+"-status2", m.status ?? "--");

    const th = Number(m.hashrate_th);

    setText(id+"-ths", fmt(m.hashrate_th, 2));
    setText(id+"-ths2", fmt(m.hashrate_th, 2));

    setText(id+"-w", fmt(m.watts, 1));
    setText(id+"-w2", fmt(m.watts, 1));
    setText(id+"-eff", m.eff_j_th ? fmt(m.eff_j_th, 2) : "--");

    // best diff badge
    const be = document.getElementById(id+"-best");
    if(be){
      if(m.best_diff){
        const meta = bestMeta(m.best_diff);
        be.textContent = `${meta.emo} ${fmtShort(m.best_diff)}`.trim();
        be.title = fmtInt(m.best_diff);
        be.classList.add("bestBadge");
        be.classList.remove("bestT","bestB","bestM","bestK");
        if(meta.cls) be.classList.add(meta.cls);
      }else{
        be.textContent = "--";
        be.title = "";
      }
    }

    setText(id+"-asic", m.asic_temp !== null ? fmt(m.asic_temp, 1) : "--");
    setText(id+"-vrm",  m.vrm_temp !== null ? fmt(m.vrm_temp, 1) : "--");

    const newA = (m.shares_accepted ?? null);

    // POOL + USER
    try{
    }catch(e){}

    // coin rain when shares increase
    try{ coinRainUpdate(id, newA, m.status); }catch(e){}
    // pool box
    try{ updatePoolBox(id, m.pool, m.user); }catch(e){}


    setText(id+"-shA", newA ?? "--");
    setText(id+"-shR", m.shares_rejected ?? "--");
    setText(id+"-err", m.error_pct !== null ? fmt(m.error_pct, 2) : "--");

    setText(id+"-freq", m.frequency ?? "--");
    setText(id+"-core", m.core_v ?? "--");
    setText(id+"-rssi", m.wifi_rssi ?? "--");
    // pool + user
setText(id+"-fan",  m.fan_rpm ?? "--");
    setText(id+"-up", fmtUptime(m.uptime_s));
    setText(id+"-ts", m.ts_human ?? "--");

    const w = Number(m.watts);
    const wMax = calcMaxW(id, w);
    setText(id+"-wMax", fmt(wMax, 0));
    setBar(id+"-pwrBar", (wMax > 0 ? w / wMax : 0), (wMax > 0 ? w / wMax > 0.85 : false));

    const t = Number(m.asic_temp);
    const tMax = 85;
    setText(id+"-tMax", tMax);
    setBar(id+"-tmpBar", (tMax > 0 ? t / tMax : 0), (tMax > 0 ? t / tMax > 0.85 : false));
  }

  // Update BTC KPIs

  // charts sequentially
  if(window.MINERS){
    for(const minerId of window.MINERS){
      const st = (miners[minerId] || {}).status || "offline";
      try{ await refreshChart(minerId, st); }catch(e){}
    }
  }
}

/* ===== init (stable) ===== */

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
