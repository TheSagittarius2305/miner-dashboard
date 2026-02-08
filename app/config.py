from dataclasses import dataclass
from pathlib import Path
import yaml

@dataclass
class AppConfig:
    raw: dict

def load_config(path: str = "config.yaml") -> AppConfig:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    Path(data["app"]["db_path"]).parent.mkdir(parents=True, exist_ok=True)
    return AppConfig(raw=data)
