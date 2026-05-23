import argparse
import html
import json
import os
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from .config import load_config
from .http_client import http_json
from .nginx_log import find_matching_request


def load_state(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(errors="ignore") or "{}")
    except Exception:
        return 0
    try:
        return int(data.get("last_id", 0) or 0)
    except Exception:
        return 0


def save_state(path: Path, last_id: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"last_id": int(last_id)}, ensure_ascii=False) + "\n")
    os.chmod(path, 0o600)


def parse_seconds(raw: str, default: int = 15) -> int:
    try:
        value = int((raw or "").strip())
    except Exception:
        return default
    return value if value > 0 else default


def parse_status_filter(raw: str) -> set[str]:
    items = set()
    for part in (raw or "").split(","):
        text = part.strip()
        if text:
            items.add(text)
    return items


def parse_bool(raw: str, default: bool = False) -> bool:
    text = str(raw or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def parse_created_at(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=UTC).astimezone()
        except Exception:
            pass

    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC).astimezone()
    return dt.astimezone()


def format_time(raw: str, display_tz: str) -> str:
    dt = parse_created_at(raw)
    if dt is None:
        return raw.strip() or "<unknown>"

    if str(display_tz or "local").strip().lower() == "utc":
        dt = dt.astimezone(UTC)
        return dt.strftime("%F %T UTC")

    return dt.strftime("%F %T %z")


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

    print(f"[monitor-db] TG send failed: HTTP {code} {raw}")
    return False


def open_db_ro(db_path: str) -> sqlite3.Connection:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


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


def fetch_latest_update(conn: sqlite3.Connection) -> sqlite3.Row | None:
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
        ORDER BY s.id DESC
        LIMIT 1
    """
    return conn.execute(sql).fetchone()


def mask_sub_path(path: str) -> str:
    text = (path or "").strip()
    if not text.startswith("/sub/"):
        return text or "<none>"

    token = text[5:]
    if len(token) <= 14:
        return f"/sub/{token}"
    return f"/sub/{token[:8]}...{token[-6:]}"


def find_nginx_match(cfg: dict, row: sqlite3.Row) -> dict | None:
    if not parse_bool(cfg.get("DB_MONITOR_LOOKUP_NGINX_IP", "true"), True):
        return None

    created_at = parse_created_at(str(row["created_at"] or ""))
    if created_at is None:
        return None

    log_path = (cfg.get("NGINX_ACCESS_LOG") or "").strip()
    lookback = parse_seconds(cfg.get("DB_MONITOR_NGINX_LOOKBACK_SECONDS", "600"), 600)
    statuses = parse_status_filter(cfg.get("DB_MONITOR_NGINX_STATUS", "200,304"))

    return find_matching_request(
        log_path=log_path,
        db_created_at=created_at,
        user_agent=str(row["user_agent"] or ""),
        window_seconds=lookback,
        allowed_statuses=statuses,
    )


def build_message(row: sqlite3.Row, display_tz: str, nginx_match: dict | None = None) -> str:
    username = (row["username"] or f"id={row['user_id']}").strip()
    status = str(row["status"] or "<none>")
    db_ip = str(row["ip"] or "<none>")
    source_ip = str(nginx_match["remote_addr"] if nginx_match else db_ip)
    hwid = str(row["hwid"] or "<none>")
    user_agent = str(row["user_agent"] or "<none>")
    created_at = format_time(str(row["created_at"] or ""), display_tz)
    expire = str(row["expire"] or "<none>")
    revoked = str(row["sub_revoked_at"] or "<none>")

    extra = ""
    if nginx_match:
        extra = (
            f"\nNginx路径：<code>{html.escape(mask_sub_path(str(nginx_match.get('path') or '')))}</code>"
            f"\nNginx状态：{html.escape(str(nginx_match.get('status') or '<none>'))}"
            f"\n响应大小：{int(nginx_match.get('body_bytes') or 0)} B"
        )

    return (
        "#订阅拉取提醒\n\n"
        f"用户：<b>{html.escape(username)}</b>\n"
        f"用户ID：{row['user_id']}\n"
        f"状态：{html.escape(status)}\n"
        f"时间：{html.escape(created_at)}\n"
        f"来源IP：<code>{html.escape(source_ip)}</code>\n"
        f"DB记录IP：<code>{html.escape(db_ip)}</code>\n"
        f"HWID：<code>{html.escape(hwid)}</code>\n"
        f"UA：<code>{html.escape(user_agent)}</code>\n"
        f"到期：{html.escape(expire)}\n"
        f"撤销时间：{html.escape(revoked)}"
        f"{extra}\n"
        f"记录ID：{row['id']}"
    )


def run_once(cfg: dict, db_path: str, state_path: Path, status_filter: set[str]) -> bool:
    conn = open_db_ro(db_path)
    try:
        last_id = load_state(state_path)
        if last_id <= 0:
            last_id = fetch_max_id(conn)
            save_state(state_path, last_id)
            print(f"[monitor-db] initialized at id={last_id}")
            return True

        rows = fetch_updates(conn, last_id)
        if not rows:
            return True

        current_id = last_id
        display_tz = cfg.get("DB_MONITOR_DISPLAY_TZ", "local")
        for row in rows:
            status = str(row["status"] or "")
            if status_filter and status not in status_filter:
                current_id = int(row["id"])
                save_state(state_path, current_id)
                continue

            nginx_match = find_nginx_match(cfg, row)
            text = build_message(row, display_tz, nginx_match=nginx_match)
            if not send_tg(cfg, text):
                return False

            current_id = int(row["id"])
            save_state(state_path, current_id)

        return True
    finally:
        conn.close()


def load_runtime_config() -> tuple[dict, str, Path, int, set[str]]:
    cfg = load_config()
    db_path = (cfg.get("PASARGUARD_DB_PATH") or "").strip() or "/var/lib/pasarguard/db.sqlite3"
    state_path = Path((cfg.get("DB_MONITOR_STATE_FILE") or "").strip() or "/var/lib/pasar-eazylink/db-monitor.state")
    poll_seconds = parse_seconds(cfg.get("DB_MONITOR_POLL_SECONDS", "15"))
    status_filter = parse_status_filter(cfg.get("SUB_NOTIFY_USER_STATUS", ""))
    return cfg, db_path, state_path, poll_seconds, status_filter


def latest_message(cfg: dict, db_path: str) -> str | None:
    conn = open_db_ro(db_path)
    try:
        row = fetch_latest_update(conn)
        if row is None:
            return None
        nginx_match = find_nginx_match(cfg, row)
        return build_message(row, cfg.get("DB_MONITOR_DISPLAY_TZ", "local"), nginx_match=nginx_match)
    finally:
        conn.close()


def run_test_mode(send: bool) -> int:
    cfg, db_path, _state_path, _poll_seconds, _status_filter = load_runtime_config()
    try:
        text = latest_message(cfg, db_path)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1
    except sqlite3.Error as exc:
        print(f"database error: {exc}")
        return 1

    if text is None:
        print("no subscription updates found")
        return 0

    print(text)
    if not send:
        return 0

    if not cfg.get("TG_BOT_TOKEN") or not cfg.get("TG_CHAT_ID"):
        print("[monitor-db] TG_BOT_TOKEN 或 TG_CHAT_ID 为空。")
        return 1

    return 0 if send_tg(cfg, text) else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pasar monitor-db")
    parser.add_argument("--test", action="store_true", help="print the latest notification without sending")
    parser.add_argument("--send-test", action="store_true", help="send the latest notification once")
    args = parser.parse_args(argv)
    if args.test and args.send_test:
        parser.error("--test and --send-test cannot be used together")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.test:
        return run_test_mode(send=False)
    if args.send_test:
        return run_test_mode(send=True)

    while True:
        try:
            cfg, db_path, state_path, poll_seconds, status_filter = load_runtime_config()
            if not cfg.get("TG_BOT_TOKEN") or not cfg.get("TG_CHAT_ID"):
                print("[monitor-db] TG_BOT_TOKEN 或 TG_CHAT_ID 为空，等待配置。")
                time.sleep(5)
                continue

            ok = run_once(cfg, db_path, state_path, status_filter)
            if not ok:
                time.sleep(5)
                continue
        except FileNotFoundError as exc:
            print(f"[monitor-db] {exc}")
            time.sleep(5)
            continue
        except sqlite3.Error as exc:
            print(f"[monitor-db] database error: {exc}")
            time.sleep(5)
            continue
        except Exception as exc:
            print(f"[monitor-db] error: {exc}")
            time.sleep(5)
            continue

        time.sleep(poll_seconds)


if __name__ == "__main__":
    sys.exit(main())
