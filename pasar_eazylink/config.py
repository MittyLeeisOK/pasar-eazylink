import os
import shlex
from pathlib import Path

CONFIG_FILE = Path("/etc/pasar-easylink.env")
TG_ENV = Path("/etc/sub-notify.env")
DEFAULT_MAP_FILE = "/etc/sub-map.tsv"

DEFAULT_CONFIG = {
    "PASAR_PANEL_HOST": "https://127.0.0.1",
    "PASAR_PANEL_PORT": "8000",
    "PASAR_API_KEY": "",
    "SHLINK_API_BASE": "https://go.mitty.space/rest/v3",
    "SHLINK_API_KEY": "",
    "SHORT_DOMAIN": "https://go.mitty.space",
    "SUB_BASE_URL": "https://pasar.mitty.space/sub",
    "TG_BOT_TOKEN": "",
    "TG_CHAT_ID": "",
    "TG_THREAD_ID": "",
    "PASARGUARD_DB_PATH": "/var/lib/pasarguard/db.sqlite3",
    "NGINX_ACCESS_LOG": "/var/log/nginx/access.log",
    "DB_MONITOR_STATE_FILE": "/var/lib/pasar-eazylink/db-monitor.state",
    "DB_MONITOR_POLL_SECONDS": "15",
    "DB_MONITOR_DEDUP_SECONDS": "120",
    "DB_MONITOR_LOOKUP_NGINX_IP": "true",
    "DB_MONITOR_NGINX_LOOKBACK_SECONDS": "600",
    "DB_MONITOR_NGINX_STATUS": "200,304",
    "LOG_MONITOR_ACCESS_LOG": "/var/log/nginx/access.log",
    "LOG_MONITOR_MAP_FILE": "/etc/sub-map.tsv",
    "LOG_MONITOR_STATUS_CODES": "200,304",
    "LOG_MONITOR_METHODS": "GET",
    "EAZYLINK_WRITE_LEGACY_MAPPING": "false",
    # Legacy keys kept for compatibility.
    "SUB_MAP_FILE": "/etc/sub-map.tsv",
    "SUB_NOTIFY_POLL_SECONDS": "15",
    "SUB_NOTIFY_STATE_FILE": "/var/lib/pasar-eazylink/db-monitor.state",
    "SUB_NOTIFY_USER_STATUS": "",
}


ALIASES = {
    "PASAR_ACCESS_TOKEN": "PASAR_API_KEY",
    "SUB_NOTIFY_STATE_FILE": "DB_MONITOR_STATE_FILE",
    "SUB_NOTIFY_POLL_SECONDS": "DB_MONITOR_POLL_SECONDS",
    "SUB_MAP_FILE": "LOG_MONITOR_MAP_FILE",
}


def parse_env_file(path: Path) -> dict:
    data = {}
    if not path.exists():
        return data

    for raw in path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        try:
            parts = shlex.split(value)
            data[key] = parts[0] if parts else ""
        except Exception:
            data[key] = value.strip("'\"")

    return data


def apply_aliases(cfg: dict):
    for old_key, new_key in ALIASES.items():
        if cfg.get(old_key) and not cfg.get(new_key):
            cfg[new_key] = cfg[old_key]

    if cfg.get("NGINX_ACCESS_LOG") and not cfg.get("LOG_MONITOR_ACCESS_LOG"):
        cfg["LOG_MONITOR_ACCESS_LOG"] = cfg["NGINX_ACCESS_LOG"]
    if cfg.get("LOG_MONITOR_ACCESS_LOG") and not cfg.get("NGINX_ACCESS_LOG"):
        cfg["NGINX_ACCESS_LOG"] = cfg["LOG_MONITOR_ACCESS_LOG"]

    if cfg.get("LOG_MONITOR_MAP_FILE") and not cfg.get("SUB_MAP_FILE"):
        cfg["SUB_MAP_FILE"] = cfg["LOG_MONITOR_MAP_FILE"]
    if cfg.get("SUB_MAP_FILE") and not cfg.get("LOG_MONITOR_MAP_FILE"):
        cfg["LOG_MONITOR_MAP_FILE"] = cfg["SUB_MAP_FILE"]

    if cfg.get("DB_MONITOR_POLL_SECONDS") and not cfg.get("SUB_NOTIFY_POLL_SECONDS"):
        cfg["SUB_NOTIFY_POLL_SECONDS"] = cfg["DB_MONITOR_POLL_SECONDS"]
    if cfg.get("DB_MONITOR_STATE_FILE") and not cfg.get("SUB_NOTIFY_STATE_FILE"):
        cfg["SUB_NOTIFY_STATE_FILE"] = cfg["DB_MONITOR_STATE_FILE"]


def write_env_file(path: Path, data: dict):
    apply_aliases(data)
    lines = []
    for key in DEFAULT_CONFIG:
        lines.append(f"{key}={shlex.quote(str(data.get(key, '')))}")

    path.write_text("\n".join(lines) + "\n")
    os.chmod(path, 0o600)


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        write_env_file(CONFIG_FILE, DEFAULT_CONFIG.copy())

    cfg = DEFAULT_CONFIG.copy()
    cfg.update(parse_env_file(CONFIG_FILE))

    if TG_ENV.exists():
        tg = parse_env_file(TG_ENV)
        changed = False

        if tg.get("BOT_TOKEN") and not cfg.get("TG_BOT_TOKEN"):
            cfg["TG_BOT_TOKEN"] = tg["BOT_TOKEN"]
            changed = True

        if tg.get("CHAT_ID") and not cfg.get("TG_CHAT_ID"):
            cfg["TG_CHAT_ID"] = tg["CHAT_ID"]
            changed = True

        if tg.get("THREAD_ID") and not cfg.get("TG_THREAD_ID"):
            cfg["TG_THREAD_ID"] = tg["THREAD_ID"]
            changed = True

        if changed:
            write_env_file(CONFIG_FILE, cfg)

    apply_aliases(cfg)
    return cfg


def save_config(cfg: dict):
    write_env_file(CONFIG_FILE, cfg)


def save_kv(key: str, value: str):
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)
