# 订阅监控与短链接管理

Subscription Monitor & Link Manager

用于 PasarGuard 的订阅短链接管理、订阅拉取监控和泄漏追踪。

## 推荐安装

```bash
curl -fsSL https://raw.githubusercontent.com/MittyLeeisOK/pasar-eazylink/main/install.sh | bash
```

## 升级

```bash
curl -fsSL https://raw.githubusercontent.com/MittyLeeisOK/pasar-eazylink/main/install.sh | bash -s -- --upgrade
```

## 卸载

```bash
curl -fsSL https://raw.githubusercontent.com/MittyLeeisOK/pasar-eazylink/main/install.sh | bash -s -- --uninstall
```

## 彻底卸载

```bash
curl -fsSL https://raw.githubusercontent.com/MittyLeeisOK/pasar-eazylink/main/install.sh | bash -s -- --purge
```

## 备用方式（Git clone）

安装：

```bash
git clone https://github.com/MittyLeeisOK/pasar-eazylink.git
cd pasar-eazylink
bash install.sh
```

升级：

```bash
cd /opt/pasar-eazylink
git pull
bash install.sh --upgrade
```

卸载：

```bash
bash /opt/pasar-eazylink/install.sh --uninstall
```

## 启动菜单

```bash
pasar easylink
```

菜单标题：`订阅监控与短链接管理`

## 订阅监控模式

- DB监控（推荐）
- 日志监控（兼容）

泄漏监控建议：优先使用 **DB监控 + Nginx IP补全**；日志监控用于回滚和兼容。

## 命令

推荐：

```bash
pasar monitor-db
pasar monitor-db --test
pasar monitor-db --send-test
```

兼容旧命令：

```bash
pasar subnotify-db
pasar subnotify-db --test
pasar subnotify-db --send-test
```

日志监控脚本：

```bash
sub-notify.sh
```

## 文件路径

- /opt/pasar-eazylink
- /etc/pasar-easylink.env
- /etc/sub-notify.env
- /etc/sub-map.tsv
- /var/lib/pasar-eazylink
- /usr/local/bin/pasar
- /usr/local/bin/sub-notify.sh

## 服务

- sub-notify-db.service
- sub-notify.service

## 安装参数

```bash
bash install.sh --help
```

支持：`--install` `--upgrade` `--uninstall` `--purge` `--yes` `--install-deps` `--enable-db-monitor` `--enable-log-monitor` `--disable-db-monitor` `--disable-log-monitor`

## 备份说明

安装脚本不在 `/root` 下创建临时/备份目录。临时目录使用 `mktemp -d` 并自动清理。
