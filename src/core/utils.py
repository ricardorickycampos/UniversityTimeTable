from __future__ import annotations
import json
from pathlib import Path
import yaml
import numpy as np

def load_config(path: Path) -> dict:
    """Parse YAML config"""
    with open(path) as f:
        return yaml.safe_load(f)

def json_default(o):
    """JSON encoder"""
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f'Not JSON serializable: {type(o)}')

def save_run_log(log_path: Path, run_log: dict):
    """Save run log to JSON file."""
    with open(log_path, 'w') as f:
        json.dump(run_log, f, indent=2, default=json_default)
