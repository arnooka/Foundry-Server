"""Turns nginx's structured per-request JSON log (see
nginx/conf.d/_logging.conf) into the dashboard's traffic charts: a live
request-type breakdown and a request-volume history, both bounded to the
last 4 hours. See docker-compose.yml's nginx-logs volume comment for why
that's enforced here in memory rather than by keeping the raw log around."""

import json
import os
import time
from collections import deque

LOG_PATH = "/var/log/app-traffic/traffic.json.log"
RETENTION_SECONDS = 4 * 60 * 60
BUCKET_SECONDS = 15 * 60  # 16 buckets across the 4-hour window
NUM_BUCKETS = RETENTION_SECONDS // BUCKET_SECONDS

# Safety valve only, not the retention mechanism: keeps the on-disk log from
# growing unbounded over a long uptime. The 4-hour window itself is enforced
# by _trim_old() below, entirely independent of how big the file gets.
_TRUNCATE_THRESHOLD_BYTES = 5_000_000

_log_offset = 0

# In-memory only, like the password-reset code elsewhere in this app (see
# docker_control.py). config-ui is a single Flask process, so this is safe,
# and a restart just starts the 4-hour window over instead of corrupting
# anything.
_events = deque()  # (timestamp, vhost, method, status, bytes) per request


def _read_new_lines() -> None:
    global _log_offset
    try:
        size = os.path.getsize(LOG_PATH)
    except OSError:
        return

    if size < _log_offset:
        _log_offset = 0  # log file was replaced/rotated out from under us

    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            f.seek(_log_offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    _events.append((
                        float(entry["time"]),
                        str(entry.get("vhost", "unknown")),
                        str(entry.get("method", "UNKNOWN")),
                        int(entry.get("status", 0)),
                        int(entry.get("bytes", 0)),
                    ))
                except (ValueError, KeyError, TypeError):
                    continue
            _log_offset = f.tell()
    except OSError:
        return

    if size > _TRUNCATE_THRESHOLD_BYTES:
        try:
            with open(LOG_PATH, "w"):
                pass
            _log_offset = 0
        except OSError:
            pass


def _trim_old() -> None:
    cutoff = time.time() - RETENTION_SECONDS
    while _events and _events[0][0] < cutoff:
        _events.popleft()


def get_traffic_stats() -> dict:
    """Everything here covers only the trailing 4 hours; anything older is
    dropped for good, matching the retention the user asked for. Bucket
    timestamps are raw epoch seconds so the browser can render them in the
    viewer's own local time instead of the container's.

    Returns:
        {
            "request_types": {"GET": 42, "POST": 3, ...},
            "timeseries": [{"time": 1234567890.0, "count": 5}, ...],  # oldest -> newest
            "total_requests": 45,
            "window_hours": 4,
        }
    """
    _read_new_lines()
    _trim_old()

    request_types: dict[str, int] = {}
    for _, _vhost, method, _status, _nbytes in _events:
        request_types[method] = request_types.get(method, 0) + 1

    now = time.time()
    bucket_counts = [0] * NUM_BUCKETS
    for ts, *_ in _events:
        idx_from_now = int((now - ts) // BUCKET_SECONDS)
        bucket_idx = NUM_BUCKETS - 1 - idx_from_now
        if 0 <= bucket_idx < NUM_BUCKETS:
            bucket_counts[bucket_idx] += 1

    timeseries = [
        {"time": now - (NUM_BUCKETS - 1 - i) * BUCKET_SECONDS, "count": count}
        for i, count in enumerate(bucket_counts)
    ]

    return {
        "request_types": request_types,
        "timeseries": timeseries,
        "total_requests": len(_events),
        "window_hours": RETENTION_SECONDS // 3600,
    }
