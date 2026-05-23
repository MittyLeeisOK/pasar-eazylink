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
    "SELECT s.id,s.user_id,s.created_at,s.user_agent,s.ip,s.hwid,u.username,u.status "
    "FROM user_subscription_updates s LEFT JOIN users u ON u.id=s.user_id ORDER BY s.id DESC LIMIT 1"
)
BATCH_SQL = (
    "SELECT s.id,s.user_id,s.created_at,s.user_agent,s.ip,s.hwid,u.username,u.status "
    "FROM user_subscription_updates s LEFT JOIN users u ON u.id=s.user_id "
    "WHERE s.id > ? ORDER BY s.id ASC LIMIT ?"
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
    if "?" in token:
        token_main, query = token.split("?", 1)
        suffix = f"?{query}"
    else:
        token_main, suffix = token, ""
    if len(token_main) <= 14:
        return path
    return f"/sub/{token_main[:8]}...{token_main[-6:]}{suffix}"


def format_sub_path(path: str) -> str:
    return mask_path(path or "")


def lookup_ip_geo(ip: str) -> str:
    ip = (ip or "").strip()
    if not ip or ip in {"127.0.0.1", "::1"}:
        return "本地/回环地址"
    code, data, _ = http_json("GET", f"https://ipwho.is/{ip}")
    if not (200 <= code < 300) or not isinstance(data, dict):
        return ""
    if data.get("success") is False:
        return ""
    country = str(data.get("country") or "").strip()
    city = str(data.get("city") or "").strip()
    region = str(data.get("region") or "").strip()
    isp = str(data.get("connection", {}).get("isp") or "").strip()
    parts = [x for x in [country, region, city, isp] if x]
    return " / ".join(parts)


def render_status(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value in {"active", "enabled", "ok"}:
        return f"✅ {value or 'active'}"
    if value in {"disabled", "inactive", "banned", "blocked"}:
        return f"⛔ {value}"
    return value or "unknown"


def to_int(value: str | None, default: int, minimum: int) -> int:
    try:
        return max(int(value or default), minimum)
    except Exception:
        return max(default, minimum)


def send_tg(cfg: dict, text: str) -> tuple[bool, int, str]:
    form = {"chat_id": cfg.get("TG_CHAT_ID", ""), "parse_mode": "HTML", "text": text}
    if cfg.get("TG_THREAD_ID"):
        form["message_thread_id"] = cfg["TG_THREAD_ID"]
    code, data, err = http_json("POST", f"https://api.telegram.org/bot{cfg.get('TG_BOT_TOKEN','')}/sendMessage", form=form)
    ok = 200 <= code < 300 and data.get("ok", True)
    return ok, code, err


def build_message(row: sqlite3.Row, cfg: dict, nginx_match: dict | None = None) -> str:
    ua_raw = str(row["user_agent"] or "").strip()
    ua = parse_user_agent(ua_raw)
    source_ip_raw = str(nginx_match["remote_addr"]) if nginx_match else ""
    source_ip = f"<code>{html.escape(source_ip_raw)}</code>" if source_ip_raw else "未匹配到 Nginx 真实IP"
    source_geo = lookup_ip_geo(source_ip_raw) if source_ip_raw else ""
    source_geo_line = f" | {html.escape(source_geo)}" if source_geo else ""
    req_path = format_sub_path(str(nginx_match["path"] or "")) if nginx_match else ""
    response_size = int(nginx_match["body_bytes"]) if nginx_match else 0
    db_ip = str(row["ip"] or "").strip()
    db_ip_tail = "（默认隐藏，没有来源IP时显示）" if db_ip in {"", "127.0.0.1", "::1"} else ""
    hwid = str(row["hwid"] or "").strip()
    hwid_line = f"\nHWID：<code>{html.escape(hwid)}</code>" if hwid and hwid.lower() not in {"none", "<none>"} else ""
    return (
        "#订阅拉取提醒\n"
        f"时间：{html.escape(format_display_time(str(row['created_at'] or ''), cfg.get('DISPLAY_TIMEZONE', 'local')))}\n"
        f"记录ID：{row['id']}\n"
        "---\n"
        f"用户：{html.escape(str(row['username'] or f'id={row['user_id']}'))}\n"
        f"用户ID：{row['user_id']}\n"
        f"状态：{html.escape(render_status(str(row['status'] or '')))}\n"
        f"IP：{source_ip}{source_geo_line}\n"
        f"DB记录IP：<code>{html.escape(db_ip)}</code>{html.escape(db_ip_tail)}{hwid_line}\n"
        f"UA：<code>{html.escape(ua_raw or '-')}</code>\n"
        f"路径：<code>{html.escape(req_path or '-')}</code>\n"
        f"响应大小：{response_size} B\n"
        "---\n"
        f"设备识别：{html.escape(ua['client'])} / {html.escape(ua['device_type'])} / {html.escape(ua['os'])} / {html.escape(str(ua.get('model') or '-'))}"
    )


def load_state(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"last_id": 0}
    try:
        return json.loads(p.read_text(errors="ignore"))
    except Exception:
        return {"last_id": 0}


def save_state(path: str, state: dict):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False))
    tmp.replace(p)


def match_nginx(target_row: sqlite3.Row, cfg: dict) -> dict | None:
    db_time = parse_db_time_utc(str(target_row["created_at"] or ""))
    if not db_time:
        return None
    statuses = {x.strip() for x in cfg.get("DB_MONITOR_NGINX_STATUS", "200,304").split(",") if x.strip()}
    return find_matching_request(
        cfg.get("NGINX_ACCESS_LOG", "/var/log/nginx/access.log"),
        db_time,
        str(target_row["user_agent"] or ""),
        to_int(cfg.get("DB_MONITOR_NGINX_LOOKBACK_SECONDS", "600"), 600, 1),
        statuses,
        to_int(cfg.get("DB_MONITOR_NGINX_TAIL_BYTES", "2097152"), 2097152, 4096),
    )


def monitor_loop(cfg: dict) -> int:
    poll = to_int(cfg.get("DB_MONITOR_POLL_SECONDS", "15"), 15, 3)
    batch = to_int(cfg.get("DB_MONITOR_BATCH_SIZE", "20"), 20, 1)
    state_file = cfg.get("DB_MONITOR_STATE_FILE", "/var/lib/pasar-eazylink/db-monitor.state")
    state = load_state(state_file)
    last_warn = {"db": 0, "tg": 0, "nginx": 0}

    while True:
        now = int(time.time())
        try:
            conn = sqlite3.connect(cfg.get("PASARGUARD_DB_PATH", ""))
            conn.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            if now - last_warn["db"] >= 300:
                print(f"[monitor-db] db unavailable: {exc}")
                last_warn["db"] = now
            time.sleep(poll)
            continue

        if not cfg.get("TG_BOT_TOKEN") or not cfg.get("TG_CHAT_ID"):
            if now - last_warn["tg"] >= 300:
                print("[monitor-db] telegram config missing")
                last_warn["tg"] = now
            conn.close()
            time.sleep(poll)
            continue

        if not Path(cfg.get("NGINX_ACCESS_LOG", "")).exists() and now - last_warn["nginx"] >= 600:
            print(f"[monitor-db] nginx log not found: {cfg.get('NGINX_ACCESS_LOG')}")
            last_warn["nginx"] = now

        try:
            rows = conn.execute(BATCH_SQL, (int(state.get("last_id", 0)), batch)).fetchall()
        except sqlite3.Error as exc:
            if now - last_warn["db"] >= 300:
                print(f"[monitor-db] db query failed: {exc}")
                last_warn["db"] = now
            conn.close()
            time.sleep(poll)
            continue

        for row in rows:
            row_id = int(row["id"])
            matched = match_nginx(row, cfg)
            text = build_message(row, cfg, matched)
            ok, code, err = send_tg(cfg, text)
            if ok:
                state["last_id"] = row_id
                save_state(state_file, state)
                print(f"[monitor-db] sent id={row_id} user={row['username'] or row['user_id']} ip={row['ip']} status={matched['status'] if matched else 'na'}")
            else:
                print(f"[monitor-db] send failed id={row_id} http={code} error={err}")
                break

        conn.close()
        time.sleep(poll)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--send-test", action="store_true")
    args = parser.parse_args(argv)
    cfg = load_config()

    try:
        conn = sqlite3.connect(cfg["PASARGUARD_DB_PATH"])
        conn.row_factory = sqlite3.Row
        row = conn.execute(LATEST_UPDATE_SQL).fetchone()
    except sqlite3.Error as exc:
        print(f"failed to open db: {exc}")
        return 1 if (args.test or args.send_test) else monitor_loop(cfg)

    if not row:
        print("no subscription updates found")
        return 0

    text = build_message(row, cfg, match_nginx(row, cfg))
    if args.test:
        print(text)
        return 0
    if args.send_test:
        print(text)
        ok, _, _ = send_tg(cfg, text)
        return 0 if ok else 1

    return monitor_loop(cfg)
