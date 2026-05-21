import os
from datetime import datetime
from pathlib import Path

from .config import DEFAULT_MAP_FILE
from .utils import short_token


def map_path(cfg: dict) -> Path:
    return Path(cfg.get("SUB_MAP_FILE") or DEFAULT_MAP_FILE)


def read_mapping(cfg: dict) -> list[dict]:
    path = map_path(cfg)
    rows = []

    if not path.exists():
        return rows

    for idx, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append({
                "line": idx,
                "token": parts[0],
                "user": parts[1],
            })

    return rows


def backup_mapping(cfg: dict):
    path = map_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    os.chmod(path, 0o600)

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup = Path(str(path) + f".bak.{ts}")
    backup.write_text(path.read_text(errors="ignore"))
    os.chmod(backup, 0o600)

    return path, backup


def add_token(cfg: dict, token: str, username: str):
    path, backup = backup_mapping(cfg)
    rows = read_mapping(cfg)

    if any(row["token"] == token for row in rows):
        print(f"Mapping 已存在该 token，未重复写入：{short_token(token)}")
        return

    with path.open("a") as f:
        f.write(f"{token}\t{username}\n")

    os.chmod(path, 0o600)
    print(f"Mapping 已追加：{short_token(token)} -> {username}")


def delete_user(cfg: dict, username: str):
    path, backup = backup_mapping(cfg)
    lines = path.read_text(errors="ignore").splitlines()

    kept = []
    removed = 0

    for line in lines:
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1] == username:
            removed += 1
            continue
        kept.append(line)

    path.write_text("\n".join(kept) + ("\n" if kept else ""))
    os.chmod(path, 0o600)

    print(f"已删除 Mapping 中用户 {username} 的 {removed} 条记录。备份：{backup}")


def show_mapping(cfg: dict, query: str = ""):
    rows = read_mapping(cfg)
    q = query.lower().strip()

    print()
    print("=== User Mapping ===")
    print("序号\t行号\t用户\ttoken")

    n = 0
    for row in rows:
        if q and q not in row["user"].lower() and q not in row["token"].lower():
            continue

        n += 1
        print(f"{n}\t{row['line']}\t{row['user']}\t{short_token(row['token'])}")

    if n == 0:
        print("无匹配记录")

    print()
