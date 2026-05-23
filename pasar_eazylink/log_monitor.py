import argparse
import json
import os
import re
import time
from pathlib import Path

from .config import load_config
from .http_client import http_json

STATE_FILE = Path("/var/lib/pasar-eazylink/log-monitor.state")
LOG_RE = re.compile(r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[[^\]]+\]\s+"(?P<method>\S+)\s+(?P<path>\S+)\s+[^\"]+"\s+(?P<status>\d{3})\s+')
TOKEN_RE = re.compile(r"/sub/([^/?#\s]+)")


def parse_set(raw: str, fallback: set[str]) -> set[str]:
    values = {x.strip().upper() for x in (raw or "").split(",") if x.strip()}
    return values if values else fallback


def parse_int(raw: str, default: int) -> int:
    try:
        value = int((raw or "").strip())
    except Exception:
        return default
    return value if value > 0 else default


def load_mapping(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            data[parts[0].strip()] = parts[1].strip()
    return data


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"offset": 0, "inode": 0}
    try:
        data = json.loads(STATE_FILE.read_text(errors="ignore") or "{}")
        return {
            "offset": int(data.get("offset", 0) or 0),
            "inode": int(data.get("inode", 0) or 0),
        }
    except Exception:
        return {"offset": 0, "inode": 0}


def save_state(offset: int, inode: int):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"offset": int(offset), "inode": int(inode)}, ensure_ascii=False) + "\n")
    os.chmod(STATE_FILE, 0o600)


def send_tg(cfg: dict, text: str) -> bool:
    form = {
        "chat_id": cfg["TG_CHAT_ID"],
        "parse_mode": "HTML",
        "text": text,
    }
    if cfg.get("TG_THREAD_ID"):
        form["message_thread_id"] = cfg["TG_THREAD_ID"]

    code, data, raw = http_json(
        "POST",
        f"https://api.telegram.org/bot{cfg['TG_BOT_TOKEN']}/sendMessage",
        form=form,
    )
    if 200 <= code < 300 and data.get("ok", True):
        return True

    print(f"[log-monitor] TG send failed: HTTP {code} {raw}")
    return False


def check_config(cfg: dict) -> tuple[bool, list[str]]:
    access_log = Path((cfg.get("LOG_MONITOR_ACCESS_LOG") or cfg.get("NGINX_ACCESS_LOG") or "").strip())
    map_file = Path((cfg.get("LOG_MONITOR_MAP_FILE") or cfg.get("SUB_MAP_FILE") or "").strip())

    errors = []
    if not access_log:
        errors.append("LOG_MONITOR_ACCESS_LOG is empty")
    elif not access_log.exists():
        errors.append(f"access log not found: {access_log}")

    if not map_file:
        errors.append("LOG_MONITOR_MAP_FILE is empty")
    elif not map_file.exists():
        errors.append(f"mapping file not found: {map_file}")

    if not cfg.get("TG_BOT_TOKEN"):
        errors.append("TG_BOT_TOKEN is empty")
    if not cfg.get("TG_CHAT_ID"):
        errors.append("TG_CHAT_ID is empty")

    return len(errors) == 0, errors


def format_message(username: str, token: str, ip: str, method: str, status: str, path: str) -> str:
    return (
        "#日志订阅拉取提醒\n\n"
        f"用户：<b>{username}</b>\n"
        f"Token：<code>{token}</code>\n"
        f"IP：<code>{ip}</code>\n"
        f"Method：{method}\n"
        f"Status：{status}\n"
        f"Path：<code>{path}</code>"
    )


def process_once(cfg: dict, dedup: dict[str, float]) -> bool:
    access_log = Path((cfg.get("LOG_MONITOR_ACCESS_LOG") or cfg.get("NGINX_ACCESS_LOG") or "/var/log/nginx/access.log").strip())
    map_file = Path((cfg.get("LOG_MONITOR_MAP_FILE") or cfg.get("SUB_MAP_FILE") or "/etc/sub-map.tsv").strip())

    if not access_log.exists():
        print(f"[log-monitor] access log not found: {access_log}")
        return True

    mapping = load_mapping(map_file)
    methods = parse_set(cfg.get("LOG_MONITOR_METHODS", "GET"), {"GET"})
    statuses = parse_set(cfg.get("LOG_MONITOR_STATUS_CODES", "200,304"), {"200", "304"})
    dedup_seconds = parse_int(cfg.get("DB_MONITOR_DEDUP_SECONDS", "120"), 120)

    stat = access_log.stat()
    state = load_state()
    offset = int(state.get("offset", 0))
    inode = int(state.get("inode", 0))

    if inode != int(stat.st_ino) or offset > int(stat.st_size):
        offset = 0

    with access_log.open("r", errors="ignore") as f:
        f.seek(offset)
        for raw in f:
            line = raw.strip()
            match = LOG_RE.match(line)
            if not match:
                continue

            method = match.group("method").upper()
            status = match.group("status").upper()
            path = match.group("path")
            ip = match.group("ip")

            if method not in methods or status not in statuses:
                continue

            token_match = TOKEN_RE.search(path)
            if not token_match:
                continue

            token = token_match.group(1)
            username = mapping.get(token)
            if not username:
                continue

            key = f"{token}|{ip}|{status}"
            now = time.time()
            if dedup.get(key) and now - dedup[key] < dedup_seconds:
                continue

            if send_tg(cfg, format_message(username, token, ip, method, status, path)):
                dedup[key] = now

        offset = f.tell()

    save_state(offset, int(stat.st_ino))
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="sub-notify.sh")
    parser.add_argument("--check-config", action="store_true", help="check runtime config and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = load_config()

    if args.check_config:
        ok, errors = check_config(cfg)
        if ok:
            print("log monitor config ok")
            return 0
        for err in errors:
            print(err)
        return 1

    dedup: dict[str, float] = {}
    poll_seconds = parse_int(cfg.get("DB_MONITOR_POLL_SECONDS", "15"), 15)

    while True:
        try:
            cfg = load_config()
            if not cfg.get("TG_BOT_TOKEN") or not cfg.get("TG_CHAT_ID"):
                print("[log-monitor] TG_BOT_TOKEN 或 TG_CHAT_ID 为空，等待配置。")
                time.sleep(5)
                continue
            process_once(cfg, dedup)
            poll_seconds = parse_int(cfg.get("DB_MONITOR_POLL_SECONDS", "15"), 15)
        except Exception as exc:
            print(f"[log-monitor] error: {exc}")
            time.sleep(5)
            continue

        time.sleep(poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
