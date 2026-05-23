# 订阅用户与短链接管理

用于 PasarGuard 的用户订阅创建、Shlink 短链接管理和订阅拉取监控。

## 核心功能
1. 快速新增用户+短链
2. 管理短链
3. DB订阅监控
4. 真实IP补全
5. Telegram提醒

## 安装
curl -fsSL https://raw.githubusercontent.com/MittyLeeisOK/pasar-eazylink/main/install.sh | bash

## 升级
curl -fsSL https://raw.githubusercontent.com/MittyLeeisOK/pasar-eazylink/main/install.sh | bash -s -- --upgrade

## 卸载
curl -fsSL https://raw.githubusercontent.com/MittyLeeisOK/pasar-eazylink/main/install.sh | bash -s -- --uninstall

## 彻底卸载
curl -fsSL https://raw.githubusercontent.com/MittyLeeisOK/pasar-eazylink/main/install.sh | bash -s -- --purge --yes

启动菜单：`pasar easylink`

订阅监控说明：只使用 PasarGuard user_subscription_updates 作为触发源。Nginx access.log 只用于补全真实来源 IP。不再使用旧 mapping 表，不再提供旧 access.log 独立通知服务。
