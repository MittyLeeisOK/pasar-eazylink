#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/opt/pasar-eazylink"

install -d "$INSTALL_DIR"
install -d "$INSTALL_DIR/pasar_eazylink"

cp -a "$PROJECT_DIR/pasar_eazylink/"*.py "$INSTALL_DIR/pasar_eazylink/"
install -m 755 "$PROJECT_DIR/bin/pasar" /usr/local/bin/pasar

if [ ! -f /etc/pasar-easylink.env ]; then
  install -m 600 "$PROJECT_DIR/config/pasar-easylink.env.example" /etc/pasar-easylink.env
  echo "Created /etc/pasar-easylink.env"
else
  echo "/etc/pasar-easylink.env already exists, skipped"
fi

python3 -m py_compile "$INSTALL_DIR/pasar_eazylink/"*.py
python3 -m py_compile /usr/local/bin/pasar

echo "Installed. Run: pasar easylink"
