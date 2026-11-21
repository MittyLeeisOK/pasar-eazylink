# 订阅用户与短链接管理

用于 PasarGuard 的用户订阅创建、Shlink 短链接管理和订阅拉取监控。

## 核心功能
1. 快速新增用户+短链
2. 管理短链
3. DB订阅监控
4. 真实IP补全
5. Telegram提醒

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

## Pasar 认证（API Key）
- 使用 PasarGuard API Key 认证（请求头 `X-Api-Key`），不再使用管理员账号密码登录。
- 在 PasarGuard 面板的 API Keys 页面创建 Key（需要用户模板读取、用户创建权限），填入 `/etc/pasar-easylink.env` 的 `PASAR_API_KEY`，或在菜单「设置 → Pasar」中修改。
- 旧版本保存在 `PASAR_API_KEY` 中的登录 access_token 不再有效，需换成 API Key。

启动菜单：`pasar easylink`
自测命令：`pasar self-test`

订阅监控说明：
- 只使用 PasarGuard `user_subscription_updates` 作为触发源。
- Nginx `access.log` 只用于补全真实来源 IP。
- 不再使用旧 mapping 表。
- 不再提供旧 `access.log` 独立通知服务。
