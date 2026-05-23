#!/usr/bin/env bash
set -e

ENABLE_SUBNOTIFY_DB="false"
for arg in "$@"; do
  case "$arg" in
    --enable-subnotify-db)
      ENABLE_SUBNOTIFY_DB="true"
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: bash install.sh [--enable-subnotify-db]" >&2
      exit 1
      ;;
  esac
done

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/opt/pasar-eazylink"
CONFIG_FILE="/etc/pasar-easylink.env"
EXAMPLE_CONFIG="$PROJECT_DIR/config/pasar-easylink.env.example"
PACKAGE_DIR="$INSTALL_DIR/pasar_eazylink"

mask_value() {
  local v="${1:-}"
  local len="${#v}"

  if [ -z "$v" ]; then
    printf "<empty>"
  elif [ "$len" -le 12 ]; then
    printf "%s" "$v"
  else
    printf "%s...%s" "${v:0:6}" "${v: -4}"
  fi
}

prompt_value() {
  local key="$1"
  local label="$2"
  local secret="${3:-false}"
  local current="${!key:-}"
  local display="$current"
  local input=""

  if [ "$secret" = "true" ]; then
    display="$(mask_value "$current")"
  fi
  if [ -z "$display" ]; then
    display="<empty>"
  fi

  if [ "$secret" = "true" ]; then
    read -rsp "${label} [当前: ${display}]: " input || true
    echo
  else
    read -rp "${label} [当前: ${display}]: " input || true
  fi

  if [ -n "$input" ]; then
    printf -v "$key" "%s" "$input"
  fi
}

write_config() {
  export PASAR_PANEL_HOST PASAR_PANEL_PORT PASAR_API_KEY SHLINK_API_BASE SHLINK_API_KEY
  export SHORT_DOMAIN SUB_BASE_URL SUB_MAP_FILE TG_BOT_TOKEN TG_CHAT_ID TG_THREAD_ID
  export PASARGUARD_DB_PATH SUB_NOTIFY_POLL_SECONDS SUB_NOTIFY_STATE_FILE SUB_NOTIFY_USER_STATUS
  export EAZYLINK_WRITE_LEGACY_MAPPING

  python3 - "$CONFIG_FILE" <<'PY'
import os
import shlex
import sys
from pathlib import Path

keys = [
    "PASAR_PANEL_HOST",
    "PASAR_PANEL_PORT",
    "PASAR_API_KEY",
    "SHLINK_API_BASE",
    "SHLINK_API_KEY",
    "SHORT_DOMAIN",
    "SUB_BASE_URL",
    "SUB_MAP_FILE",
    "TG_BOT_TOKEN",
    "TG_CHAT_ID",
    "TG_THREAD_ID",
    "PASARGUARD_DB_PATH",
    "SUB_NOTIFY_POLL_SECONDS",
    "SUB_NOTIFY_STATE_FILE",
    "SUB_NOTIFY_USER_STATUS",
    "EAZYLINK_WRITE_LEGACY_MAPPING",
]

path = Path(sys.argv[1])
lines = [f"{key}={shlex.quote(os.environ.get(key, ''))}" for key in keys]
path.write_text("\n".join(lines) + "\n")
path.chmod(0o600)
PY
}

guide_config() {
  local source_file="$EXAMPLE_CONFIG"

  if [ -f "$CONFIG_FILE" ]; then
    source_file="$CONFIG_FILE"
  fi

  set -a
  # shellcheck disable=SC1090
  . "$source_file"
  set +a

  : "${PASAR_PANEL_HOST:=https://127.0.0.1}"
  : "${PASAR_PANEL_PORT:=8000}"
  : "${PASAR_API_KEY:=}"
  : "${SHORT_DOMAIN:=https://go.mitty.space}"
  : "${SHLINK_API_BASE:=${SHORT_DOMAIN%/}/rest/v3}"
  : "${SHLINK_API_KEY:=}"
  : "${SUB_BASE_URL:=https://pasar.mitty.space/sub}"
  : "${SUB_MAP_FILE:=/etc/sub-map.tsv}"
  : "${TG_BOT_TOKEN:=}"
  : "${TG_CHAT_ID:=}"
  : "${TG_THREAD_ID:=}"
  : "${PASARGUARD_DB_PATH:=/var/lib/pasarguard/db.sqlite3}"
  : "${SUB_NOTIFY_POLL_SECONDS:=15}"
  : "${SUB_NOTIFY_STATE_FILE:=/var/lib/pasar-eazylink/sub-notify.state}"
  : "${SUB_NOTIFY_USER_STATUS:=}"
  : "${EAZYLINK_WRITE_LEGACY_MAPPING:=false}"
  local original_short_domain="$SHORT_DOMAIN"
  local original_shlink_base="$SHLINK_API_BASE"

  echo
  echo "=== Eazy Link 配置引导 ==="
  prompt_value PASAR_PANEL_HOST "Pasar Panel 地址"
  prompt_value PASAR_PANEL_PORT "Pasar Panel 端口"
  prompt_value PASAR_API_KEY "Pasar Access Token（可留空，后续可登录获取）" true
  prompt_value SHORT_DOMAIN "短链域名"
  PASAR_PANEL_HOST="${PASAR_PANEL_HOST%/}"
  SHORT_DOMAIN="${SHORT_DOMAIN%/}"
  if [ "$SHORT_DOMAIN" != "$original_short_domain" ] && [ "$original_shlink_base" = "${original_short_domain%/}/rest/v3" ]; then
    SHLINK_API_BASE="${SHORT_DOMAIN%/}/rest/v3"
  fi
  SHLINK_API_BASE="${SHLINK_API_BASE%/}"
  prompt_value SHLINK_API_BASE "Shlink API Base"
  SHLINK_API_BASE="${SHLINK_API_BASE%/}"
  prompt_value SHLINK_API_KEY "Shlink API Key" true
  prompt_value SUB_BASE_URL "订阅基础地址"
  SUB_BASE_URL="${SUB_BASE_URL%/}"
  prompt_value SUB_MAP_FILE "Mapping 表路径"
  prompt_value TG_BOT_TOKEN "TG Bot Token" true
  prompt_value TG_CHAT_ID "TG Chat ID" true
  prompt_value TG_THREAD_ID "TG Thread ID（可留空）"
  prompt_value PASARGUARD_DB_PATH "PasarGuard SQLite 路径"
  prompt_value SUB_NOTIFY_POLL_SECONDS "提醒轮询间隔秒数"
  prompt_value SUB_NOTIFY_STATE_FILE "提醒状态文件路径"
  prompt_value SUB_NOTIFY_USER_STATUS "提醒用户状态过滤（逗号分隔，可留空）"
  prompt_value EAZYLINK_WRITE_LEGACY_MAPPING "Legacy Mapping 自动写入（true/false）"

  write_config
  echo "配置已保存到 ${CONFIG_FILE}"
}

install -d "$INSTALL_DIR"
if [ "$PROJECT_DIR" != "$INSTALL_DIR" ]; then
  rm -rf "$PACKAGE_DIR"
  cp -a "$PROJECT_DIR/pasar_eazylink" "$INSTALL_DIR/"
else
  echo "Source directory is already $INSTALL_DIR, skip copying package files"
fi
install -m 755 "$PROJECT_DIR/bin/pasar" /usr/local/bin/pasar
install -m 755 "$PROJECT_DIR/bin/sub-notify" /usr/local/bin/sub-notify

created_config=""
if [ ! -f "$CONFIG_FILE" ]; then
  install -m 600 "$EXAMPLE_CONFIG" "$CONFIG_FILE"
  echo "Created ${CONFIG_FILE}"
  created_config="yes"
else
  echo "${CONFIG_FILE} already exists, skipped"
fi

if [ -t 0 ]; then
  if [ "$created_config" = "yes" ]; then
    guide_config
  else
    read -rp "检测到已有配置，是否现在引导填写？[y/N]: " edit_config
    if [[ "$edit_config" =~ ^[Yy]$ ]]; then
      guide_config
    fi
  fi
else
  echo "非交互环境，跳过配置引导。请手动编辑 ${CONFIG_FILE}"
fi

python3 -m py_compile "$PACKAGE_DIR/"*.py
python3 -m py_compile /usr/local/bin/pasar
python3 -m py_compile /usr/local/bin/sub-notify
echo "安装检查通过：脚本已编译。"

if command -v systemctl >/dev/null 2>&1; then
  install -d /etc/systemd/system
  install -m 644 "$PROJECT_DIR/systemd/sub-notify-db.service" /etc/systemd/system/sub-notify-db.service
  systemctl daemon-reload >/dev/null 2>&1 || true
  if [ "$ENABLE_SUBNOTIFY_DB" = "true" ]; then
    systemctl enable --now sub-notify-db.service
  fi
fi

hash -r 2>/dev/null || true
echo "Installed. Run:"
echo "  pasar easylink"
echo "  pasar subnotify-db --test"
echo
echo "To enable DB-based subscription notification:"
echo "  systemctl enable --now sub-notify-db.service"
echo "  journalctl -u sub-notify-db.service -f"
