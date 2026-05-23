import argparse
import html
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import load_config
from .device import parse_user_agent
from .http_client import http_json
from .nginx_log import find_matching_request


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
    row = conn.execute(
        "SELECT s.id,s.user_id,s.created_at,s.user_agent,s.ip,u.username,u.status "
        "FROM user_subscription_updates s LEFT JOIN users u ON u.id=s.user_id ORDER BY s.id DESC LIMIT 1"
    ).fetchone()
    if not row:
        print("no subscription updates found")
        return 0

    nginx_match = None
    if str(cfg.get("DB_MONITOR_LOOKUP_NGINX_IP", "true")).lower() == "true":
        db_time = parse_db_time_utc(str(row["created_at"] or ""))
        if db_time:
            nginx_match = find_matching_request(
                cfg.get("NGINX_ACCESS_LOG", "/var/log/nginx/access.log"),
                db_time,
                str(row["user_agent"] or ""),
                int(cfg.get("DB_MONITOR_NGINX_LOOKBACK_SECONDS", "600")),
                {x.strip() for x in cfg.get("DB_MONITOR_NGINX_STATUS", "200,304").split(",") if x.strip()},
            )

    text = build_message(row, cfg, nginx_match)
    print(text)
    if args.send_test:
        return 0 if send_tg(cfg, text) else 1
    return 0
