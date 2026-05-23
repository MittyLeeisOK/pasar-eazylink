# Pasar Eazy Link

A lightweight SSH menu tool for managing PasarGuard subscription links, Shlink short URLs, and DB-based subscription notifications.

## Features

- Create, update, and delete Eazy Link short URLs
- Browse and manage Shlink short links
- DB-based Telegram subscription notifications from PasarGuard SQLite (`user_subscription_updates`)
- Legacy mapping tools for `/etc/sub-map.tsv` compatibility
- Manage PasarGuard API, Shlink API, Telegram, and notification settings from CLI

## Recommended notification mode

推荐使用 **DB-based subscription notification**，不要再依赖 Nginx access.log `/sub/` 方案。

原因是 access.log 只能证明有人访问了 `/sub/` 路径，不能可靠表示真实的订阅更新事件；当前项目直接读取 PasarGuard SQLite 中的 `user_subscription_updates` 并 `JOIN users`，可以拿到更准确的用户、状态、时间与订阅信息。

## Install

```bash
tmp_dir="$(mktemp -d /tmp/pasar-eazylink.XXXXXX)" && (
  trap 'rm -rf "$tmp_dir"' EXIT
  git clone https://github.com/MittyLeeisOK/pasar-eazylink.git "$tmp_dir" \
    && cd "$tmp_dir" \
    && sudo bash install.sh
)
```

如需安装后立即启用 DB 通知服务：

```bash
sudo bash install.sh --enable-subnotify-db
```

安装过程中会引导填写 `/etc/pasar-easylink.env` 配置参数；若配置文件已存在，安装脚本不会强制覆盖，请手动补充新增配置项。

安装完成后可运行：

```bash
pasar easylink
pasar subnotify-db --test
```

如需启用 DB-based subscription notification：

```bash
systemctl enable --now sub-notify-db.service
journalctl -u sub-notify-db.service -f
```

## Notification-related config

`/etc/pasar-easylink.env` 中与 DB 通知相关的配置：

- `PASARGUARD_DB_PATH`：PasarGuard SQLite 路径（默认 `/var/lib/pasarguard/db.sqlite3`）
- `SUB_NOTIFY_STATE_FILE`：增量读取状态文件（默认 `/var/lib/pasar-eazylink/sub-notify.state`）
- `SUB_NOTIFY_POLL_SECONDS`：轮询间隔秒数（默认 `15`）
- `SUB_NOTIFY_USER_STATUS`：状态过滤；留空表示不过滤，`active` 表示只通知 active，`active,on_hold` 表示只通知这两类状态
- `TG_BOT_TOKEN` / `TG_CHAT_ID` / `TG_THREAD_ID`：Telegram 推送配置

## Legacy mapping compatibility

`/etc/sub-map.tsv` 和 `mapping.py` 仍然保留，用于旧通知链路或历史兼容。

新增配置：

```bash
EAZYLINK_WRITE_LEGACY_MAPPING='false'
```

- `false`：新增/更新 Eazy Link 时不写入 `/etc/sub-map.tsv`
- `true`：保持旧行为，继续写入 token -> username mapping

CLI 中的 Mapping 功能已移动到 **Legacy Mapping 工具** 菜单。
