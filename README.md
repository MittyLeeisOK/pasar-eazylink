# Pasar Eazy Link

A lightweight SSH menu tool for managing PasarGuard subscription links, Shlink short URLs, and subscription access notification mapping.

## Features

- Create Eazy Link from PasarGuard user template
- Generate hard-to-guess short links using username + 4-6 digit suffix
- Update Eazy Link without deleting old token mappings
- Delete user mapping and Shlink short links
- View current user mapping
- View Shlink short link list
- Modify or delete a single Shlink short link
- Manage PasarGuard API, Shlink API, and Telegram notification settings
- SQLite-based subscription pull notifications from PasarGuard (`user_subscription_updates`)

## Install

```bash
tmp_dir="$(mktemp -d /tmp/pasar-eazylink.XXXXXX)" && (
  trap 'rm -rf "$tmp_dir"' EXIT
  git clone https://github.com/MittyLeeisOK/pasar-eazylink.git "$tmp_dir" \
    && cd "$tmp_dir" \
    && sudo bash install.sh
)
```

安装过程中会引导填写 `/etc/pasar-easylink.env` 配置参数；若需修改，可再次运行 `pasar easylink` -> 设置。
若安装完成后提示 `pasar: command not found`，可先执行 `/usr/local/bin/pasar easylink`，并检查 `/usr/local/bin` 是否在 `PATH` 中（必要时执行 `hash -r`）。

安装后会同时部署 `sub-notify.service`，通过轮询 PasarGuard SQLite 数据库的 `user_subscription_updates` 表发送 TG 提醒（替代旧的 access.log `/sub/` 识别逻辑）。
相关参数位于 `/etc/pasar-easylink.env`：

- `PASARGUARD_DB_PATH`：PasarGuard SQLite 路径（默认 `/var/lib/pasarguard/db.sqlite3`）
- `SUB_NOTIFY_POLL_SECONDS`：轮询间隔秒数
- `SUB_NOTIFY_STATE_FILE`：增量读取状态文件
- `SUB_NOTIFY_USER_STATUS`：可选状态过滤（逗号分隔，留空代表不过滤）
