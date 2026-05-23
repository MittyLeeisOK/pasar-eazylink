import os
import re
from datetime import datetime
from pathlib import Path

LOG_RE = re.compile(
    r'^(?P<remote_addr>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+"(?P<method>\S+)\s+(?P<path>\S+)\s+[^\"]*"\s+(?P<status>\d{3})\s+(?P<body_bytes>\S+)\s+"(?P<referer>[^\"]*)"\s+"(?P<user_agent>[^\"]*)"'
)


def parse_nginx_time(raw: str) -> datetime:
    return datetime.strptime(raw.strip(), "%d/%b/%Y:%H:%M:%S %z")


def parse_nginx_access_line(line: str) -> dict | None:
    m = LOG_RE.match(line.strip())
    if not m:
        return None

    body_bytes_raw = m.group("body_bytes")
    body_bytes = int(body_bytes_raw) if body_bytes_raw.isdigit() else 0

    try:
        ts = parse_nginx_time(m.group("time"))
    except Exception:
        return None

    return {
        "remote_addr": m.group("remote_addr"),
        "time": ts,
        "method": m.group("method").upper(),
        "path": m.group("path"),
        "status": m.group("status"),
        "body_bytes": body_bytes,
        "referer": m.group("referer"),
        "user_agent": m.group("user_agent"),
    }


def read_tail(path: str, max_bytes: int = 5 * 1024 * 1024) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []

    size = p.stat().st_size
    offset = max(0, size - max_bytes)
    with p.open("rb") as f:
        if offset > 0:
            f.seek(offset)
            _ = f.readline()
        data = f.read()

    return data.decode(errors="ignore").splitlines()


def _to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return dt.astimezone(datetime.now().astimezone().tzinfo)


def find_matching_request(
    log_path: str,
    db_created_at: datetime,
    user_agent: str,
    window_seconds: int,
    allowed_statuses: set[str],
) -> dict | None:
    if not log_path or not os.path.exists(log_path):
        return None

    db_local = _to_local(db_created_at)
    rows = read_tail(log_path)
    candidates = []

    for line in rows:
        item = parse_nginx_access_line(line)
        if not item:
            continue

        if not item["path"].startswith("/sub/"):
            continue

        if item["method"] not in {"GET", "HEAD"}:
            continue

        if allowed_statuses and item["status"] not in allowed_statuses:
            continue

        item_local = _to_local(item["time"])
        delta = abs((item_local - db_local).total_seconds())
        if delta > max(1, int(window_seconds or 600)):
            continue

        ua_match = item["user_agent"] == (user_agent or "")
        is_get = item["method"] == "GET"
        status_200 = item["status"] == "200"
        score = (
            1 if ua_match else 0,
            1 if is_get else 0,
            1 if status_200 else 0,
            int(item["body_bytes"]),
            -float(delta),
        )

        candidates.append((score, item, delta))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best = candidates[0][1].copy()
    best["delta_seconds"] = candidates[0][2]
    return best
