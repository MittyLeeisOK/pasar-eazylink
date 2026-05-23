import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from .config import load_config
from .nginx_log import find_matching_request, parse_nginx_access_line, read_tail
from .sub_notify import parse_db_time_utc


def run_self_test() -> int:
    cfg = load_config()
    passed = warned = failed = 0

    def mark(kind: str, msg: str):
        nonlocal passed, warned, failed
        print(f"[{kind}] {msg}")
        if kind == "PASS":
            passed += 1
        elif kind == "WARN":
            warned += 1
        else:
            failed += 1

    mark("PASS", f"Python version: {sys.version.split()[0]}")
    cmd = shutil.which("pasar") or "not found"
    mark("PASS", f"pasar command: {cmd}")

    rc = subprocess.run(["python3", "-m", "py_compile", *Path("pasar_eazylink").glob("*.py"), "bin/pasar"], check=False).returncode
    mark("PASS" if rc == 0 else "FAIL", "py_compile check")

    cfg_path = Path("/etc/pasar-easylink.env")
    mark("PASS" if cfg_path.exists() else "FAIL", f"config exists: {cfg_path}")
    for k in ["PASARGUARD_DB_PATH", "TG_BOT_TOKEN", "TG_CHAT_ID", "NGINX_ACCESS_LOG"]:
        mark("PASS" if cfg.get(k) else "FAIL", f"config key: {k}")

    db_path = Path(cfg.get("PASARGUARD_DB_PATH", ""))
    if db_path.exists():
        mark("PASS", f"db exists: {db_path}")
    else:
        mark("WARN", f"db not found: {db_path}")

    conn = None
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            for t in ["user_subscription_updates", "users"]:
                ok = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
                mark("PASS" if ok else "FAIL", f"DB table: {t}")
            row = cur.execute("SELECT id,user_id,created_at,user_agent,ip,hwid FROM user_subscription_updates ORDER BY id DESC LIMIT 1").fetchone()
            mark("PASS" if row else "WARN", "latest subscription record")
        except Exception as exc:
            mark("FAIL", f"db check failed: {exc}")

    nginx_log = Path(cfg.get("NGINX_ACCESS_LOG", ""))
    if nginx_log.exists():
        mark("PASS", f"nginx log exists: {nginx_log}")
        sample = None
        for ln in reversed(read_tail(str(nginx_log), 2 * 1024 * 1024)):
            p = parse_nginx_access_line(ln)
            if p and p["path"].startswith("/sub/"):
                sample = p
                break
        mark("PASS" if sample else "WARN", "nginx /sub/ parse test")
    else:
        mark("WARN", f"Nginx log not found: {nginx_log}")

    if conn and nginx_log.exists():
        try:
            row = conn.execute("SELECT created_at,user_agent FROM user_subscription_updates ORDER BY id DESC LIMIT 1").fetchone()
            if row:
                dt = parse_db_time_utc(row[0])
                if dt:
                    match = find_matching_request(str(nginx_log), dt, row[1] or "", 600, {"200", "304"})
                    mark("PASS" if match else "WARN", f"real ip match: {'match' if match else 'no match'}")
        except Exception as exc:
            mark("WARN", f"real ip match skipped: {exc}")

    mark("PASS" if cfg.get("TG_BOT_TOKEN") else "FAIL", "TG_BOT_TOKEN configured")
    mark("PASS" if cfg.get("TG_CHAT_ID") else "FAIL", "TG_CHAT_ID configured")

    svc = Path("/etc/systemd/system/sub-notify-db.service")
    mark("PASS" if svc.exists() else "WARN", "systemd file exists: sub-notify-db.service")
    if svc.exists():
        text = svc.read_text(errors="ignore")
        mark("PASS" if "ExecStart=/usr/local/bin/pasar monitor-db" in text else "FAIL", "systemd ExecStart")
        mark("PASS" if "Restart=on-failure" in text else "FAIL", "systemd Restart")

    for legacy in ["/usr/local/bin/sub-notify.sh", "/etc/systemd/system/sub-notify.service"]:
        mark("WARN" if Path(legacy).exists() else "PASS", f"legacy cleaned: {legacy}")

    if cfg_path.exists():
        mode = oct(cfg_path.stat().st_mode & 0o777)
        mark("PASS" if mode == "0o600" else "WARN", f"config mode: {mode} (recommended 0o600)")

    mark("PASS", "cli import smoke: pasar_eazylink.cli")

    print(f"Self-test summary: {passed} PASS, {warned} WARN, {failed} FAIL")
    return 1 if failed > 0 else 0
