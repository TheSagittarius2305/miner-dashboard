from flask import Blueprint, render_template, current_app, abort, jsonify, request
from datetime import datetime, timedelta

bp = Blueprint("web", __name__)

def ts_human(ts: int) -> str:
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "-"

def _eff_j_th(watts, ths):
    try:
        if watts is None or ths in (None, 0):
            return None
        return float(watts) / float(ths)
    except Exception:
        return None

def _latest_per_miner(conn):
    rows = conn.execute("""
      SELECT s.*
      FROM miner_snapshot s
      JOIN (
        SELECT miner_id, MAX(ts) AS max_ts
        FROM miner_snapshot
        GROUP BY miner_id
      ) x
      ON s.miner_id = x.miner_id AND s.ts = x.max_ts
      ORDER BY s.miner_id
    """).fetchall()
    out = {}
    for r in rows:
        d = dict(r)
        d["ts_human"] = ts_human(d.get("ts"))
        d["eff_j_th"] = _eff_j_th(d.get("watts"), d.get("hashrate_th"))
        out[d["miner_id"]] = d
    return out

@bp.get("/")
def dashboard():
    # nowy “bajer” dashboard korzysta z JS i API, tu tylko renderujemy shell
    cfg = current_app.config["CFG"]
    miners = cfg["miners"]
    price = (cfg.get("electricity") or {}).get("price_eur_per_kwh", 0.0)
    return render_template("dashboard_pro.html", miners=miners, price=price)

@bp.get("/miner/<miner_id>")
def miner_detail(miner_id: str):
    cfg_miners = {m["id"]: m for m in current_app.config["CFG"]["miners"]}
    if miner_id not in cfg_miners:
        abort(404)

    conn = current_app.config["DB"]

    latest_row = conn.execute(
        "SELECT * FROM miner_snapshot WHERE miner_id=? ORDER BY ts DESC LIMIT 1",
        (miner_id,),
    ).fetchone()

    history_rows = conn.execute(
        "SELECT * FROM miner_snapshot WHERE miner_id=? ORDER BY ts DESC LIMIT 200",
        (miner_id,),
    ).fetchall()

    latest = dict(latest_row) if latest_row else None
    if latest:
        latest["ts_human"] = ts_human(latest.get("ts"))
        latest["eff_j_th"] = _eff_j_th(latest.get("watts"), latest.get("hashrate_th"))

    history = []
    for r in history_rows:
        d = dict(r)
        d["ts_human"] = ts_human(d.get("ts"))
        d["eff_j_th"] = _eff_j_th(d.get("watts"), d.get("hashrate_th"))
        history.append(d)

    return render_template("miner.html", miner=cfg_miners[miner_id], latest=latest, history=history)

@bp.get("/api/status")
def api_status():
    cfg = current_app.config["CFG"]
    conn = current_app.config["DB"]
    latest = _latest_per_miner(conn)

    # fallback: compute error_pct from shares if device doesn't provide it (e.g. NerdQaxe++)
    for _mid, _m in (latest or {}).items():
        try:
            if _m.get('error_pct') is None:
                acc = _m.get('shares_accepted')
                rej = _m.get('shares_rejected')
                if acc is not None and rej is not None:
                    acc_i = int(acc)
                    rej_i = int(rej)
                    tot = acc_i + rej_i
                    if tot > 0:
                        _m['error_pct'] = round((rej_i / tot) * 100.0, 2)
        except Exception:
            pass


    price = float((cfg.get("electricity") or {}).get("price_eur_per_kwh", 0.0))
    total_w = sum((latest[mid].get("watts") or 0.0) for mid in latest)
    eur_day = (total_w / 1000.0) * 24.0 * price
    eur_month = eur_day * 30.0

    return jsonify({
        "now": datetime.now().strftime("%H:%M:%S"),
        "total_w": total_w,
        "eur_day": eur_day,
        "eur_month": eur_month,
        "miners": latest
    })

@bp.get("/api/history/<miner_id>")
def api_history(miner_id: str):
    hours = int(request.args.get("hours", 24))
    since_ts = int((datetime.now() - timedelta(hours=hours)).timestamp())

    conn = current_app.config["DB"]
    rows = conn.execute("""
        SELECT ts, hashrate_th, asic_temp, vrm_temp, watts
        FROM miner_snapshot
        WHERE miner_id=? AND ts>=?
        ORDER BY ts ASC
    """, (miner_id, since_ts)).fetchall()

    return jsonify([
        {
            "ts": r["ts"],
            "time": ts_human(r["ts"]),
            "hashrate": r["hashrate_th"],
            "asic_temp": r["asic_temp"],
            "vrm_temp": r["vrm_temp"],
            "watts": r["watts"],
        }
        for r in rows
    ])
