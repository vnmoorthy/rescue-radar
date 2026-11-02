"""Load .env without a shell, so values are never echoed."""
import os
from pathlib import Path


def load_env(path=Path(__file__).resolve().parent.parent / ".env"):
    """Read KEY=value lines from .env into os.environ. A missing .env is fine: real environment variables still work."""
    path = Path(path)
    lines = path.read_text().splitlines() if path.exists() else []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)
    os.environ.setdefault("BASELINE_MODEL", "claude-opus-5-5")
    return os.environ
