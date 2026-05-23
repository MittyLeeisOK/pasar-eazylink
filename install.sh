#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/MittyLeeisOK/pasar-eazylink.git"
INSTALL_DIR="/opt/pasar-eazylink"
BIN_PASAR="/usr/local/bin/pasar"
DB_SERVICE_FILE="/etc/systemd/system/sub-notify-db.service"
OLD_BIN_SUB_NOTIFY="/usr/local/bin/sub-notify.sh"
OLD_SERVICE_FILE="/etc/systemd/system/sub-notify.service"
CONFIG_FILE="/etc/pasar-easylink.env"
LEGACY_ENV_FILE="/etc/sub-notify.env"
MAPPING_FILE="/etc/sub-map.tsv"
STATE_DIR="/var/lib/pasar-eazylink"

ACTION="install"
YES="false"
INSTALL_DEPS="false"
ENABLE_DB_MONITOR="false"
DISABLE_DB_MONITOR="false"
TMP_DIR=""

usage() {
  cat <<'EOF_USAGE'
Usage: bash install.sh [options]

Options:
  --install               Install files (default), keep existing config/data.
  --upgrade               Upgrade files, keep existing config/data.
  --uninstall             Remove program and DB monitor service files, keep config/data.
  --purge                 Remove all files, config and state.
  --yes                   Skip interactive confirmation.
  --install-deps          Allow apt install of git/python3/curl.
  --enable-db-monitor     Enable and start sub-notify-db.service after install.
  --disable-db-monitor    Disable and stop sub-notify-db.service after install.
  --help                  Show this help.
EOF_USAGE
}

cleanup() {
  if [ -n "${TMP_DIR:-}" ] && [ -d "$TMP_DIR" ]; then
    rm -rf "$TMP_DIR"
  fi
}

trap cleanup EXIT

for arg in "$@"; do
  case "$arg" in
    --install)
      ACTION="install"
      ;;
    --upgrade)
      ACTION="upgrade"
      ;;
    --uninstall)
      ACTION="uninstall"
      ;;
    --purge)
      ACTION="purge"
      ;;
    --yes)
      YES="true"
      ;;
    --install-deps)
      INSTALL_DEPS="true"
      ;;
    --enable-db-monitor|--enable-subnotify-db)
      ENABLE_DB_MONITOR="true"
      ;;
    --disable-db-monitor)
      DISABLE_DB_MONITOR="true"
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root (or use sudo)." >&2
  exit 1
fi

if [ "$INSTALL_DEPS" = "true" ]; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    apt-get install -y git python3 curl
  else
    echo "--install-deps is only supported on apt-based systems." >&2
    exit 1
  fi
fi

ensure_tmp() {
  if [ -z "${TMP_DIR:-}" ]; then
    TMP_DIR="$(mktemp -d /tmp/pasar-eazylink-install.XXXXXX)"
  fi
}

normalize_lf() {
  local workdir="$1"
  find "$workdir" -type f \( -name '*.sh' -o -name '*.py' -o -path '*/bin/*' -o -name '*.service' \) -print0 | xargs -0 sed -i 's/\r$//'
}

merge_env_defaults() {
  local target="$1"
  local example="$2"

  python3 - "$target" "$example" <<'PY'
import re
import shlex
import sys
from pathlib import Path


def parse(path: Path):
    data = {}
    lines = []
    if not path.exists():
        return data, lines
    for raw in path.read_text(errors="ignore").splitlines():
        lines.append(raw)
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            continue
        try:
            parts = shlex.split(value)
            data[key] = parts[0] if parts else ""
        except Exception:
            data[key] = value.strip("'\"")
    return data, lines


target = Path(sys.argv[1])
example = Path(sys.argv[2])
example_data, _ = parse(example)

target.parent.mkdir(parents=True, exist_ok=True)
if not target.exists():
    lines = [f"{k}={shlex.quote(v)}" for k, v in example_data.items()]
    target.write_text("\n".join(lines) + "\n")
    target.chmod(0o600)
    raise SystemExit(0)

existing_data, existing_lines = parse(target)
missing_lines = []
for key, value in example_data.items():
    if key not in existing_data:
        missing_lines.append(f"{key}={shlex.quote(value)}")

if missing_lines:
    if existing_lines and existing_lines[-1].strip() != "":
        existing_lines.append("")
    existing_lines.extend(missing_lines)
    target.write_text("\n".join(existing_lines) + "\n")

target.chmod(0o600)
PY
}

cleanup_old_legacy() {
  if command -v systemctl >/dev/null 2>&1; then
    systemctl disable --now sub-notify.service >/dev/null 2>&1 || true
  fi

  rm -f "$OLD_BIN_SUB_NOTIFY"
  rm -f "$OLD_SERVICE_FILE"

  if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload >/dev/null 2>&1 || true
  fi

  if [ -f "$MAPPING_FILE" ]; then
    echo "旧 mapping 文件 /etc/sub-map.tsv 已不再使用。可手动删除。"
  fi
}

remove_runtime_files() {
  if command -v systemctl >/dev/null 2>&1; then
    systemctl disable --now sub-notify-db.service >/dev/null 2>&1 || true
    systemctl disable --now sub-notify.service >/dev/null 2>&1 || true
  fi

  rm -f "$BIN_PASAR"
  rm -f "$DB_SERVICE_FILE"
  rm -f "$OLD_BIN_SUB_NOTIFY"
  rm -f "$OLD_SERVICE_FILE"
  rm -f /usr/local/bin/sub-notify
  rm -rf "$INSTALL_DIR"

  if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload >/dev/null 2>&1 || true
  fi
}

run_uninstall() {
  remove_runtime_files

  echo "已卸载程序与服务文件。"
  echo "默认保留："
  echo "  /etc/pasar-easylink.env"
  echo "  /var/lib/pasar-eazylink"

  if [ -f "$MAPPING_FILE" ]; then
    echo "  /etc/sub-map.tsv（已不再使用，默认保留）"
    echo "旧 mapping 文件 /etc/sub-map.tsv 已不再使用。可手动删除。"
  fi

  echo
  echo "如需彻底清理，请执行："
  echo "  bash install.sh --purge --yes"
}

run_purge() {
  if [ "$YES" != "true" ]; then
    echo "This will remove all configs and state files. Type YES to continue:"
    read -r confirm
    if [ "$confirm" != "YES" ]; then
      echo "Cancelled."
      exit 1
    fi
  fi

  remove_runtime_files
  rm -f "$CONFIG_FILE"
  rm -f "$LEGACY_ENV_FILE"
  rm -f "$MAPPING_FILE"
  rm -rf "$STATE_DIR"

  echo "Purge completed."
}

resolve_source_dir() {
  local script_path script_dir
  script_path="${BASH_SOURCE[0]:-$0}"
  script_dir="$(cd "$(dirname "$script_path")" && pwd)"

  if [ -d "$script_dir/pasar_eazylink" ] && [ -d "$script_dir/bin" ] && [ -d "$script_dir/systemd" ]; then
    echo "$script_dir"
    return
  fi

  if ! command -v git >/dev/null 2>&1; then
    echo "git is required. Run with --install-deps to install dependencies." >&2
    exit 1
  fi

  ensure_tmp
  local repo_dir="$TMP_DIR/repo"
  git clone "$REPO_URL" "$repo_dir"
  echo "$repo_dir"
}

install_files() {
  local source_dir="$1"
  local stage_dir=""

  normalize_lf "$source_dir"

  if [ "$source_dir" != "$INSTALL_DIR" ]; then
    ensure_tmp
    stage_dir="$TMP_DIR/stage"
    mkdir -p "$stage_dir"
    cp -a "$source_dir"/. "$stage_dir"/
    rm -rf "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
    cp -a "$stage_dir"/. "$INSTALL_DIR"/
  else
    echo "Source directory is already install directory, skip self-copy"
  fi

  normalize_lf "$INSTALL_DIR"

  install -d /usr/local/bin
  install -m 755 "$INSTALL_DIR/bin/pasar" "$BIN_PASAR"

  install -d /etc/systemd/system
  install -m 644 "$INSTALL_DIR/systemd/sub-notify-db.service" "$DB_SERVICE_FILE"

  mkdir -p "$STATE_DIR"

  merge_env_defaults "$CONFIG_FILE" "$INSTALL_DIR/config/pasar-easylink.env.example"

  cleanup_old_legacy

  if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload >/dev/null 2>&1 || true

    if [ "$ENABLE_DB_MONITOR" = "true" ]; then
      systemctl enable --now sub-notify-db.service
    fi
    if [ "$DISABLE_DB_MONITOR" = "true" ]; then
      systemctl disable --now sub-notify-db.service
    fi
  fi

  python3 -m py_compile "$INSTALL_DIR/pasar_eazylink"/*.py "$BIN_PASAR"

  hash -r 2>/dev/null || true
  echo "订阅与短链管理 v0.9.0 安装完成。"
  echo "运行命令："
  echo "  pasar easylink"
  echo "  pasar monitor-db --test"
}

case "$ACTION" in
  uninstall)
    run_uninstall
    ;;
  purge)
    run_purge
    ;;
  install|upgrade)
    SOURCE_DIR="$(resolve_source_dir)"
    install_files "$SOURCE_DIR"
    ;;
  *)
    echo "Unsupported action: $ACTION" >&2
    exit 1
    ;;
esac
