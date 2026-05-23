# 订阅与短链管理 v0.9.0

聚焦三项核心能力：

- 一键快速新增 PasarGuard 用户并生成短链接
- 管理已有短链接
- 基于 PasarGuard DB 记录进行订阅拉取监控（可选 Nginx 日志真实 IP 补全）

## 安装

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
curl -fsSL https://raw.githubusercontent.com/MittyLeeisOK/pasar-eazylink/main/install.sh | bash -s -- --purge --yes
```

## 启动菜单

```bash
pasar easylink
```

菜单标题：`订阅与短链管理 v0.9.0`

## DB 监控命令

```bash
pasar monitor-db
pasar monitor-db --test
pasar monitor-db --send-test
```

## 安装参数

```bash
bash install.sh --help
```

支持：`--install` `--upgrade` `--uninstall` `--purge` `--yes` `--install-deps` `--enable-db-monitor` `--disable-db-monitor`
