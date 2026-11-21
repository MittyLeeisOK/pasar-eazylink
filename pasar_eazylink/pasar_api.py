import json

from .http_client import http_json

# PasarGuard (v5.6+) authenticates API keys via the X-Api-Key header
# (it also accepts "Authorization: ApiKey <key>"). No username/password login.
API_KEY_HELP = (
    "请在 PasarGuard 面板的 API Keys 页面创建 API Key，"
    "然后在「设置 → Pasar → PASAR_API_KEY」填入，"
    "或直接写入 /etc/pasar-easylink.env。"
)


def panel_base(cfg: dict) -> str:
    return f"{cfg['PASAR_PANEL_HOST'].rstrip('/')}:{cfg['PASAR_PANEL_PORT']}"


def api_key(cfg: dict) -> str:
    return (cfg.get("PASAR_API_KEY") or "").strip()


def looks_like_jwt(value: str) -> bool:
    return value.startswith("eyJ") and value.count(".") == 2


def pasar_headers(cfg: dict) -> dict:
    return {
        "X-Api-Key": api_key(cfg),
    }


def ensure_api_key(cfg: dict) -> bool:
    if api_key(cfg):
        return True
    print("未配置 PASAR_API_KEY。")
    print(API_KEY_HELP)
    return False


def api(cfg: dict, method: str, path: str, payload=None):
    if not ensure_api_key(cfg):
        return 0, {}, "no api key"

    code, data, raw = http_json(
        method,
        f"{panel_base(cfg)}{path}",
        headers=pasar_headers(cfg),
        payload=payload,
    )

    if code in (401, 403):
        if looks_like_jwt(api_key(cfg)):
            print("PASAR_API_KEY 里保存的是旧版账号密码登录得到的 access_token，已不再支持。")
        else:
            print(f"Pasar API Key 无效、已过期、已停用或权限不足（HTTP {code}）。")
        print(API_KEY_HELP)

    return code, data, raw


def list_templates(cfg: dict):
    code, data, raw = api(cfg, "GET", "/api/user_templates")

    if code != 200:
        print(f"读取模板失败，HTTP {code}")
        if raw:
            print(raw)
        return None

    print()
    print("=== 当前 User Templates ===")

    for template in data:
        gb = (template.get("data_limit") or 0) / 1024 / 1024 / 1024
        days = (template.get("expire_duration") or 0) / 86400
        disabled = " disabled" if template.get("is_disabled") else ""
        print(
            f"{template.get('id')}\t"
            f"{template.get('name')}\t"
            f"{gb:.2f}GB\t"
            f"{days:.1f}天\t"
            f"groups={template.get('group_ids')}{disabled}"
        )

    print()
    return data


def find_subscription_url(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "subscription_url" and isinstance(value, str) and "/sub/" in value:
                return value

        for value in obj.values():
            result = find_subscription_url(value)
            if result:
                return result

    elif isinstance(obj, list):
        for value in obj:
            result = find_subscription_url(value)
            if result:
                return result

    return ""


def create_user_from_template(cfg: dict, username: str, template_id: int, note: str = ""):
    payload = {
        "username": username,
        "user_template_id": template_id,
        "note": note or None,
    }

    code, data, raw = api(cfg, "POST", "/api/user/from_template", payload)

    if code == 409:
        print(f"Pasar 用户已存在：{username}")
        print(raw)
        return None

    if code not in (200, 201):
        print(f"创建 Pasar 用户失败，HTTP {code}")
        print(raw)
        return None

    long_url = find_subscription_url(data)
    if not long_url:
        print("用户已创建，但 API 响应中没有找到 subscription_url。")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return None

    return long_url


def test_api(cfg: dict):
    list_templates(cfg)
