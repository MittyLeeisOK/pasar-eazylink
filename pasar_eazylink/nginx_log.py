import re
from datetime import datetime
from pathlib import Path

LOG_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] '
    r'"(?P<method>[A-Z]+) (?P<path>\S+) [^"]+" (?P<status>\d{3}) (?P<body>\d+|-) '
    r'"[^"]*" "(?P<ua>[^"]*)"'
)


def parse_nginx_time(raw: str) -> datetime:
    return datetime.strptime(raw, "%d/%b/%Y:%H:%M:%S %z")


def parse_nginx_access_line(line: str) -> dict | None:
    match = LOG_RE.search(line.strip())
    if not match:
        return None

    data = match.groupdict()
    return {
        "remote_addr": data["ip"],
        "time": parse_nginx_time(data["time"]),
        "method": data["method"],
        "path": data["path"],
        "status": data["status"],
        "body_bytes": int(data["body"]) if data["body"].isdigit() else 0,
        "user_agent": data["ua"],
        "raw": line.rstrip("\n"),
    }


def read_tail(path: str, max_bytes: int = 2 * 1024 * 1024) -> list[str]:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return []

    with p.open("rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - max_bytes))
        return fh.read().decode(errors="ignore").splitlines()


def find_matching_request(
    log_path: str,
    db_created_at: datetime,
    user_agent: str,
    window_seconds: int,
    allowed_statuses: set[str],
    tail_bytes: int = 2 * 1024 * 1024,
    db_ip: str = "",
    username: str = "",
) -> dict | None:
    db_local = db_created_at.astimezone()
    target_ua = user_agent or ""
    statuses = {s.strip() for s in allowed_statuses if s and s.strip()}
    target_ip = (db_ip or "").strip()
    target_username = (username or "").strip()
    if not statuses:
        statuses = {"200", "304"}

    candidates: list[tuple] = []
    for line in read_tail(log_path, tail_bytes):
        row = parse_nginx_access_line(line)
        if not row:
            continue
        if not row["path"].startswith("/sub/"):
            continue
        if row["method"] not in {"GET", "HEAD"}:
            continue
        if row["status"] not in statuses:
            continue

        diff = abs((row["time"].astimezone() - db_local).total_seconds())
        if diff > window_seconds:
            continue

        path_no_query = row["path"].split("?", 1)[0].rstrip("/")
        username_path = f"/sub/{target_username}".rstrip("/")
        path_user_match = bool(target_username) and path_no_query == username_path

        candidates.append(
            (
                path_user_match,
                bool(target_ip) and row["remote_addr"] == target_ip,
                bool(target_ua) and row["user_agent"] == target_ua,
                -diff,
                row["method"] == "GET",
                row["status"] == "200",
                row["body_bytes"],
                row,
            )
        )

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][-1]
