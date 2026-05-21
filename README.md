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

## Install

```bash
git clone https://github.com/MittyLeeisOK/pasar-eazylink.git && cd pasar-eazylink && sudo bash install.sh
```

安装过程中会引导填写 `/etc/pasar-easylink.env` 配置参数；若需修改，可再次运行 `pasar easylink` -> 设置。
若安装完成后提示 `pasar: command not found`，可先执行 `/usr/local/bin/pasar easylink`，并检查 `/usr/local/bin` 是否在 `PATH` 中（必要时执行 `hash -r`）。
