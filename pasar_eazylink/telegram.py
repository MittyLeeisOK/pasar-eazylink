import json
import os
import shlex
from datetime import datetime

from .config import TG_ENV, parse_env_file
from .http_client import http_json


def sync_env(cfg: dict):
    old = parse_env_file(TG_ENV)
    old = {k: v for k, v in old.items() if k not in ("BOT_TOKEN", "CHAT_ID", "THREAD_ID")}

    lines = [
        f"BOT_TOKEN={shlex.quote(cfg.get('TG_BOT_TOKEN', ''))}",
        f"CHAT_ID={shlex.quote(cfg.get('TG_CHAT_ID', ''))}",
        f"THREAD_ID={shlex.quote(cfg.get('TG_THREAD_ID', ''))}",
    ]

    for key, value in old.items():
        lines.append(f"{key}={shlex.quote(value)}")

    TG_ENV.write_text("\n".join(lines) + "\n")
    os.chmod(TG_ENV, 0o600)

    os.system("systemctl restart sub-notify.service >/dev/null 2>&1")
    print("TG 配置已同步到 /etc/sub-notify.env，并尝试重启 sub-notify.service。")


def test(cfg: dict):
    if not cfg.get("TG_BOT_TOKEN") or not cfg.get("TG_CHAT_ID"):
        print("TG Bot Token 或 Chat ID 为空。")
        return

    text = (
        "#EazyLink测试\n\n"
        "用户：<b>test</b>\n"
        "状态：配置测试\n"
        f"时间：{datetime.now().strftime('%F %T')}"
    )

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

    print(f"HTTP {code}")
    if data:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(raw)
