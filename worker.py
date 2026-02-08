import time
from app.config import load_config
from app.db import connect, init_db
from app.miners import bitaxe

def main():
    cfg = load_config().raw
    conn = connect(cfg["app"]["db_path"])
    init_db(conn)

    miners = cfg["miners"]
    interval = int(cfg["app"]["poll_interval_sec"])

    while True:
        ts = int(time.time())

        for m in miners:
            mid = m["id"]
            base_url = m["base_url"]
            mtype = m["type"]

            try:
                if mtype == "bitaxe":
                    snap = bitaxe.fetch(base_url)["parsed"]
                else:
                    snap = {"status": "unknown"}

                conn.execute(
                    """INSERT INTO miner_snapshot
                       (miner_id, ts,
                        hashrate_th, best_diff, best_session_diff,
                        pool, user,
                        asic_temp, vrm_temp,
                        volts, amps, watts,
                        frequency, core_v,
                        shares_accepted, shares_rejected, error_pct,
                        uptime_s, fan_rpm, wifi_rssi,
                        status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        mid, ts,
                        snap.get("hashrate_th"),
                        snap.get("best_diff"),
                        snap.get("best_session_diff"),
                        snap.get("pool"),
                        snap.get("user"),
                        snap.get("asic_temp"),
                        snap.get("vrm_temp"),
                        snap.get("volts"),
                        snap.get("amps"),
                        snap.get("watts"),
                        snap.get("frequency"),
                        snap.get("core_v"),
                        snap.get("shares_accepted"),
                        snap.get("shares_rejected"),
                        snap.get("error_pct"),
                        snap.get("uptime_s"),
                        snap.get("fan_rpm"),
                        snap.get("wifi_rssi"),
                        snap.get("status", "online"),
                    ),
                )
                conn.commit()

            except Exception:
                conn.execute(
                    "INSERT INTO miner_snapshot (miner_id, ts, status) VALUES (?, ?, ?)",
                    (mid, ts, "offline"),
                )
                conn.commit()

        time.sleep(interval)

if __name__ == "__main__":
    main()
