import argparse
import html
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import load_config
from .device import parse_user_agent
from .http_client import http_json
from .nginx_log import find_matching_request

LATEST_UPDATE_SQL = (
    "SELECT s.id,s.user_id,s.created_at,s.user_agent,s.ip,u.username,u.status "
    "FROM user_subscription_updates s LEFT JOIN users u ON u.id=s.user_id ORDER BY s.id DESC LIMIT 1"
)


def parse_db_time_utc(raw: str) -> datetime | None:
    try:
        return datetime.strptime((raw or "").split(".")[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def format_display_time(raw: str, tz_name: str | None) -> str:
    dt = parse_db_time_utc(raw)
    if not dt:
        return raw or "<unknown>"

    try:
        tz = datetime.now().astimezone().tzinfo if not tz_name or tz_name == "local" else ZoneInfo(tz_name)
    except Exception:
        tz = datetime.now().astimezone().tzinfo

    try:
        return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return raw or "<unknown>"


def mask_path(path: str) -> str:
    if not path.startswith("/sub/"):
        return path
    token = path[5:]
    if len(token) <= 14:
        return path
    return f"/sub/{token[:8]}...{token[-6:]}"


def is_true(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() == "true"


def to_int(value: str | None, default: int, minimum: int) -> int:
    try:
        return max(int(value or default), minimum)
    except Exception:
        return max(default, minimum)


def send_tg(cfg: dict, text: str) -> bool:
    form = {"chat_id": cfg["TG_CHAT_ID"], "parse_mode": "HTML", "text": text}
    if cfg.get("TG_THREAD_ID"):
        form["message_thread_id"] = cfg["TG_THREAD_ID"]
    code, data, _ = http_json("POST", f"https://api.telegram.org/bot{cfg['TG_BOT_TOKEN']}/sendMessage", form=form)
    return 200 <= code < 300 and data.get("ok", True)


def build_message(row: sqlite3.Row, cfg: dict, nginx_match: dict | None = None) -> str:
    ua = parse_user_agent(str(row["user_agent"] or ""))

    source_ip = f"<code>{html.escape(str(nginx_match['remote_addr']))}</code>" if nginx_match else "未匹配到 Nginx 真实IP"
    nginx_lines = ""
    if nginx_match:
        nginx_lines = (
            f"\nNginx路径：<code>{html.escape(mask_path(nginx_match['path']))}</code>"
            f"\nNginx状态：{html.escape(str(nginx_match['status']))}"
            f"\n响应大小：{int(nginx_match['body_bytes'])} B"
        )

    username = str(row["username"] or f"id={row['user_id']}")
    status = str(row["status"] or "")
    db_ip = str(row["ip"] or "")

    return (
        "#订阅拉取提醒\n\n"
        f"用户：<b>{html.escape(username)}</b>\n"
        f"用户ID：{row['user_id']}\n"
        f"状态：{html.escape(status)}\n\n"
        f"来源IP：{source_ip}\n"
        f"DB记录IP：<code>{html.escape(db_ip)}</code>\n"
        f"设备：{html.escape(ua['client'])} / {html.escape(ua['device_type'])}\n"
        f"系统：{html.escape(ua['os'])}\n"
        f"型号：{html.escape(ua['model'])}\n"
        f"UA摘要：{html.escape(ua['summary'])}"
        f"{nginx_lines}\n\n"
        f"时间：{html.escape(format_display_time(str(row['created_at'] or ''), cfg.get('DISPLAY_TIMEZONE', 'local')))}\n"
        f"记录ID：{row['id']}"
    )


def fetch_latest(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(LATEST_UPDATE_SQL).fetchone()


def load_state(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"last_id": 0, "last_sent_at": {}}
    try:
        return json.loads(p.read_text(errors="ignore"))
    except Exception:
        return {"last_id": 0, "last_sent_at": {}}


def save_state(path: str, state: dict):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--send-test", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config()
    try:
        conn = sqlite3.connect(cfg["PASARGUARD_DB_PATH"])
    except sqlite3.Error as exc:
        print(f"failed to open db: {exc}")
        return 1
    conn.row_factory = sqlite3.Row

    row = fetch_latest(conn)
    if not row:
        print("no subscription updates found")
        return 0

    lookup_nginx_ip = is_true(cfg.get("DB_MONITOR_LOOKUP_NGINX_IP", "true"))
    nginx_log = cfg.get("NGINX_ACCESS_LOG", "/var/log/nginx/access.log")
    nginx_lookback_seconds = to_int(cfg.get("DB_MONITOR_NGINX_LOOKBACK_SECONDS", "600"), 600, 1)
    nginx_status_set = {x.strip() for x in cfg.get("DB_MONITOR_NGINX_STATUS", "200,304").split(",") if x.strip()}

    def match_nginx(target_row: sqlite3.Row) -> dict | None:
        if not lookup_nginx_ip:
            return None
        db_time = parse_db_time_utc(str(target_row["created_at"] or ""))
        if not db_time:
            return None
        return find_matching_request(
            nginx_log,
            db_time,
            str(target_row["user_agent"] or ""),
            nginx_lookback_seconds,
            nginx_status_set,
        )

    text = build_message(row, cfg, match_nginx(row))
    if args.test:
        print(text)
        return 0
    if args.send_test:
        print(text)
        return 0 if send_tg(cfg, text) else 1

    poll = to_int(cfg.get("DB_MONITOR_POLL_SECONDS", "15"), 15, 3)
    dedup = to_int(cfg.get("DB_MONITOR_DEDUP_SECONDS", "120"), 120, 1)
    state_file = cfg.get("DB_MONITOR_STATE_FILE", "/var/lib/pasar-eazylink/db-monitor.state")
    state = load_state(state_file)

    while True:
        latest = fetch_latest(conn)
        if latest:
            row_id = int(latest["id"])
            key = str(latest["user_id"])
            now_ts = int(time.time())
            last_sent = int(state.get("last_sent_at", {}).get(key, 0))
            if row_id > int(state.get("last_id", 0)) and now_ts - last_sent >= dedup:
                latest_text = build_message(latest, cfg, match_nginx(latest))
                if send_tg(cfg, latest_text):
                    state["last_id"] = row_id
                    state.setdefault("last_sent_at", {})[key] = now_ts
                    save_state(state_file, state)
        time.sleep(poll)
