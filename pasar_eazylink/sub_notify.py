import html
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from .config import load_config
from .http_client import http_json


def load_state(path: Path) -> int:
    if not path.exists():
        return 0

    try:
        data = json.loads(path.read_text(errors="ignore") or "{}")
    except Exception:
        return 0

    value = data.get("last_id", 0)
    try:
        return int(value)
    except Exception:
        return 0


def save_state(path: Path, last_id: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"last_id": int(last_id)}, ensure_ascii=False) + "\n")
    os.chmod(path, 0o600)


def parse_seconds(raw: str) -> int:
    try:
        value = int((raw or "").strip())
    except Exception:
        return 15
    return value if value > 0 else 15


def parse_status_filter(raw: str) -> set[str]:
    items = set()
    for part in (raw or "").split(","):
        text = part.strip()
        if text:
            items.add(text)
    return items


def format_time(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "<unknown>"

    dt = None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt)
            break
        except Exception:
            pass

    if dt is None:
        return raw
    return dt.strftime("%F %T")


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

    print(f"[sub-notify] TG send failed: HTTP {code} {raw}")
    return False


def fetch_max_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM user_subscription_updates").fetchone()
    return int(row[0] or 0)


def fetch_updates(conn: sqlite3.Connection, last_id: int) -> list[sqlite3.Row]:
    sql = """
        SELECT
            s.id,
            s.user_id,
            s.created_at,
            s.user_agent,
            s.ip,
            s.hwid,
            u.username,
            u.status,
            u.expire,
            u.sub_revoked_at
        FROM user_subscription_updates AS s
        LEFT JOIN users AS u ON u.id = s.user_id
        WHERE s.id > ?
        ORDER BY s.id ASC
        LIMIT 200
    """
    return conn.execute(sql, (last_id,)).fetchall()


def build_message(row: sqlite3.Row) -> str:
    username = (row["username"] or f"id={row['user_id']}").strip()
    status = str(row["status"] or "<none>")
    ip = str(row["ip"] or "<none>")
    hwid = str(row["hwid"] or "<none>")
    user_agent = str(row["user_agent"] or "<none>")
    created_at = format_time(str(row["created_at"] or ""))
    expire = str(row["expire"] or "<none>")
    revoked = str(row["sub_revoked_at"] or "<none>")

    return (
        "#订阅拉取提醒\n\n"
        f"用户：<b>{html.escape(username)}</b>\n"
        f"用户ID：{row['user_id']}\n"
        f"状态：{html.escape(status)}\n"
        f"时间：{html.escape(created_at)}\n"
        f"IP：<code>{html.escape(ip)}</code>\n"
        f"HWID：<code>{html.escape(hwid)}</code>\n"
        f"UA：<code>{html.escape(user_agent)}</code>\n"
        f"到期：{html.escape(expire)}\n"
        f"撤销时间：{html.escape(revoked)}\n"
        f"记录ID：{row['id']}"
    )


def run_once(cfg: dict, db_path: str, state_path: Path, status_filter: set[str]) -> bool:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        last_id = load_state(state_path)
        if last_id <= 0:
            last_id = fetch_max_id(conn)
            save_state(state_path, last_id)
            print(f"[sub-notify] initialized at id={last_id}")
            return True

        rows = fetch_updates(conn, last_id)
        if not rows:
            return True

        current_id = last_id
        for row in rows:
            status = str(row["status"] or "")
            if status_filter and status not in status_filter:
                current_id = int(row["id"])
                save_state(state_path, current_id)
                continue

            text = build_message(row)
            if not send_tg(cfg, text):
                return False

            current_id = int(row["id"])
            save_state(state_path, current_id)

        return True
    finally:
        conn.close()


def main():
    while True:
        try:
            cfg = load_config()
            if not cfg.get("TG_BOT_TOKEN") or not cfg.get("TG_CHAT_ID"):
                print("[sub-notify] TG_BOT_TOKEN 或 TG_CHAT_ID 为空，等待配置。")
                time.sleep(5)
                continue

            db_path = (cfg.get("PASARGUARD_DB_PATH") or "").strip() or "/var/lib/pasarguard/db.sqlite3"
            state_path = Path((cfg.get("SUB_NOTIFY_STATE_FILE") or "").strip() or "/var/lib/pasar-eazylink/sub-notify.state")
            poll_seconds = parse_seconds(cfg.get("SUB_NOTIFY_POLL_SECONDS", "15"))
            status_filter = parse_status_filter(cfg.get("SUB_NOTIFY_USER_STATUS", ""))
            ok = run_once(cfg, db_path, state_path, status_filter)
            if not ok:
                time.sleep(5)
                continue
        except Exception as exc:
            print(f"[sub-notify] error: {exc}")
            time.sleep(5)
            continue

        time.sleep(poll_seconds)
