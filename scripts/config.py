"""Shared settings from config/sim.json. CROWD_MAP_DIR overrides map_data_dir."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "sim.json"


def load():
    cfg = json.loads(CONFIG_PATH.read_text())
    cfg["map_data_dir"] = Path(os.environ.get("CROWD_MAP_DIR", cfg["map_data_dir"]))
    return cfg


def capacity_ppm(width_m, cfg):
    """Free-flow capacity of a corridor, people per minute."""
    return width_m * cfg["capacity"]["specific_flow_pms"] * 60
