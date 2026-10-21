"""How often one report link may be opened: 60 times a minute, per process.

Keyed by the link's token hash and counted only once the link has been
found, so nobody without the token can spend a link's budget: a flood of
junk tokens never takes a real link offline, and the dictionary holds only
links that exist. The expensive part of an open, assembling the report,
happens at most `LIMIT` times a minute per link per instance.

There is no limit per address. uvicorn runs without `--forwarded-allow-ips`,
so the address it sees is Cloud Run's front end, or the self-hosted nginx,
for every visitor: a per-address limit would be one bucket for the world,
which a script could empty to keep every client out of every report.
Trusting the proxy's `X-Forwarded-For` per deployment is AHM-98; a limit per
address can follow it.

Process-local, as `auth/device_access.py`'s cache is: a second instance
keeps its own count, which is sound for a bound on cost.
"""

import time

LIMIT = 60
WINDOW_SECONDS = 60.0

# token hash -> (when its window started, opens counted in it)
_windows: dict[str, tuple[float, int]] = {}


def allow(key: str) -> bool:
    """Count one open of the link `key` names, in a fixed window; False once
    it has had `LIMIT` in the current one."""
    now = time.monotonic()
    started, count = _windows.get(key, (now, 0))
    if now - started >= WINDOW_SECONDS:
        started, count = now, 0
    if count >= LIMIT:
        return False
    _windows[key] = (started, count + 1)
    return True


def clear() -> None:
    """Forget every count. Used by tests."""
    _windows.clear()
