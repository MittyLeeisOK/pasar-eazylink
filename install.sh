#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR=/opt/pasar-eazylink
BIN=/usr/local/bin/pasar
DB_SERVICE=/etc/systemd/system/sub-notify-db.service
OLD_BIN=/usr/local/bin/sub-notify.sh
OLD_SERVICE=/etc/systemd/system/sub-notify.service
CONFIG=/etc/pasar-easylink.env
STATE=/var/lib/pasar-eazylink
REPO_TARBALL_URL="https://codeload.github.com/MittyLeeisOK/pasar-eazylink/tar.gz/refs/heads/main"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-}" != "dumb" ]; then
  GREEN='\033[32m'; YELLOW='\033[33m'; RED='\033[31m'; RESET='\033[0m'
else
  GREEN=''; YELLOW=''; RED=''; RESET=''
fi

ok() { echo -e "${GREEN}[OK] $*${RESET}"; }
warn() { echo -e "${YELLOW}[WARN] $*${RESET}"; }
err() { echo -e "${RED}[ERROR] $*${RESET}"; }

ACTION=install
YES=false
ENABLE_DB_MONITOR=false
DISABLE_DB_MONITOR=false
INSTALL_DEPS=false

for a in "$@"; do
  case "$a" in
    --install) ACTION=install ;;
    --upgrade) ACTION=upgrade ;;
    --uninstall) ACTION=uninstall ;;
    --purge) ACTION=purge ;;
    --yes) YES=true ;;
    --install-deps) INSTALL_DEPS=true ;;
    --enable-db-monitor) ENABLE_DB_MONITOR=true ;;
    --disable-db-monitor) DISABLE_DB_MONITOR=true ;;
    --help)
      echo "--install --upgrade --uninstall --purge --yes --install-deps --enable-db-monitor --disable-db-monitor --help"
      exit 0
      ;;
    *)
      echo "Unknown: $a"
      exit 1
      ;;
  esac
done

[ "$(id -u)" -eq 0 ] || { err "root required"; exit 1; }

cleanup_old() {
  systemctl disable --now sub-notify.service >/dev/null 2>&1 || true
  rm -f "$OLD_BIN" "$OLD_SERVICE"
  systemctl daemon-reload >/dev/null 2>&1 || true
}

restart_db_monitor_if_needed() {
  if systemctl is-active --quiet sub-notify-db.service; then
    if systemctl restart sub-notify-db.service; then
      ok "已重启 sub-notify-db.service，使新版本立即生效。"
    else
      warn "检测到 sub-notify-db.service 正在运行，但重启失败，请手动执行：systemctl restart sub-notify-db.service"
    fi
  else
    warn "sub-notify-db.service 未运行。本次安装/升级不会自动启动服务。"
  fi
}

remove_runtime() {
  systemctl disable --now sub-notify-db.service >/dev/null 2>&1 || true
  cleanup_old
  rm -f "$BIN" "$DB_SERVICE"
  rm -rf "$INSTALL_DIR"
  systemctl daemon-reload >/dev/null 2>&1 || true
}

stage_source() {
  local stage_dir
  stage_dir="$(mktemp -d)"

  if [ -f "./bin/pasar" ] && [ -d "./pasar_eazylink" ]; then
    cp -a . "$stage_dir/src"
    echo "$stage_dir/src"
    return 0
  fi

  local tarball="$stage_dir/repo.tar.gz"
  if ! curl -fsSL "$REPO_TARBALL_URL" -o "$tarball"; then
    echo "下载项目源码失败：$REPO_TARBALL_URL"
    rm -rf "$stage_dir"
    exit 1
  fi

  tar -xzf "$tarball" -C "$stage_dir"
  local extracted
  extracted="$(find "$stage_dir" -maxdepth 1 -mindepth 1 -type d -name 'pasar-eazylink-*' | head -n1)"
  if [ -z "$extracted" ] || [ ! -f "$extracted/bin/pasar" ]; then
    echo "解压后的源码结构不正确，安装终止"
    rm -rf "$stage_dir"
    exit 1
  fi

  echo "$extracted"
}

if [ "$ACTION" = uninstall ]; then
  remove_runtime
  ok "卸载完成。"
  warn "已保留 $CONFIG 与 $STATE"
  exit 0
fi

if [ "$ACTION" = purge ]; then
  [ "$YES" = true ] || { echo "need --yes"; exit 1; }
  remove_runtime
  rm -f "$CONFIG"
  rm -rf "$STATE"
  exit 0
fi

mkdir -p "$INSTALL_DIR" "$STATE"
SRC_DIR="$(stage_source)"
cp -a "$SRC_DIR"/. "$INSTALL_DIR/"

install -m 755 "$INSTALL_DIR/bin/pasar" "$BIN"
install -m 644 "$INSTALL_DIR/systemd/sub-notify-db.service" "$DB_SERVICE"
[ -f "$CONFIG" ] || install -m 600 "$INSTALL_DIR/config/pasar-easylink.env.example" "$CONFIG"

cleanup_old
ok "安装完成。运行：pasar easylink"
restart_db_monitor_if_needed

[ "$ENABLE_DB_MONITOR" = true ] && systemctl enable --now sub-notify-db.service || true
[ "$DISABLE_DB_MONITOR" = true ] && systemctl disable --now sub-notify-db.service || true
