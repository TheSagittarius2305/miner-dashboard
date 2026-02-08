import requests

def get_json(url: str, timeout: float = 3.5) -> dict:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()
