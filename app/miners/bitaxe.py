from .client import get_json

def _to_volts(voltage_field):
    if voltage_field is None:
        return None
    try:
        v = float(voltage_field)
        return v / 1000.0 if v > 100 else v
    except Exception:
        return None

def _to_ths(hashrate_field):
    if hashrate_field is None:
        return None
    try:
        gh = float(hashrate_field)  # AxeOS: GH/s
        return gh / 1000.0 if gh > 50 else gh
    except Exception:
        return None

def _pick(d: dict, *keys):
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d:
            return d[k]
    return None

def fetch(base_url: str) -> dict:
    base = base_url.rstrip("/")
    raw = None

    for path in ("/api/system/info", "/api/system/stats"):
        try:
            raw = get_json(base + path)
            if isinstance(raw, dict) and ("hashRate" in raw or "bestDiff" in raw or "power" in raw):
                break
        except Exception:
            raw = None

    if not isinstance(raw, dict):
        return {"parsed": {"status": "offline"}, "raw": raw}

    power = _pick(raw, "power")
    volts = _to_volts(_pick(raw, "voltage"))

    amps = _pick(raw, "currentA")
    if amps is not None:
        try:
            amps = float(amps)
        except Exception:
            amps = None

    if amps is None and power is not None and volts not in (None, 0):
        try:
            amps = float(power) / float(volts)
        except Exception:
            amps = None

    parsed = {
        "status": "online",

        "hashrate_th": _to_ths(_pick(raw, "hashRate")),
        "best_diff": _pick(raw, "bestDiff"),
        "best_session_diff": _pick(raw, "bestSessionDiff"),

        "asic_temp": _pick(raw, "temp"),
        "vrm_temp": _pick(raw, "vrTemp"),

        "watts": power,
        "volts": volts,
        "amps": amps,

        "frequency": _pick(raw, "frequency"),
        "core_v": _pick(raw, "coreVoltageActual", "coreVoltage"),

        "pool": _pick(raw, "stratumURL"),
        "user": _pick(raw, "stratumUser"),

        "shares_accepted": _pick(raw, "sharesAccepted"),
        "shares_rejected": _pick(raw, "sharesRejected"),
        "error_pct": _pick(raw, "errorPercentage"),

        "uptime_s": _pick(raw, "uptimeSeconds"),
        "fan_rpm": _pick(raw, "fanrpm"),
        "wifi_rssi": _pick(raw, "wifiRSSI"),

        "version": _pick(raw, "version", "axeOSVersion"),
        "model": _pick(raw, "deviceModel", "boardVersion"),
        "ip": _pick(raw, "ipv4", "hostip"),
    }

    return {"parsed": parsed, "raw": raw}
