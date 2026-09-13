from pathlib import Path
from datetime import datetime, timezone

def snapshot_dir(raw_root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    path = raw_root / stamp
    path.mkdir(parents=True, exist_ok=False)
    return path
