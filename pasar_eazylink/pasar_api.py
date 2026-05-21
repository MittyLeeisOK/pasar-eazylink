import getpass
import json

from .config import save_config
from .http_client import http_json


def panel_base(cfg: dict) -> str:
    return f"{cfg['PASAR_PANEL_HOST'].rstrip('/')}:{cfg['PASAR_PANEL_PORT']}"


def pasar_headers(cfg: dict) -> dict:
    return {
        "Authorization": f"Bearer {cfg.get('PASAR_API_KEY', '')}",
    }


def login(cfg: dict) -> bool:
    username = input("Pasar Admin username: ").strip()
    password = getpass.getpass("Pasar Admin password: ")

    code, data, raw = http_json(
        "POST",
        f"{panel_base(cfg)}/api/admin/token",
        form={
            "username": username,
            "password": password,
        },
    )

    token = data.get("access_token", "")
    if code == 200 and token:
        cfg["PASAR_API_KEY"] = token
        save_config(cfg)
        print("Pasar 登录成功，access_token 已保存。")
        return True

    print(f"Pasar 登录失败，HTTP {code}")
    if raw:
        print(raw)
    return False


def ensure_token(cfg: dict) -> bool:
    if cfg.get("PASAR_API_KEY"):
        return True
    return login(cfg)


def api(cfg: dict, method: str, path: str, payload=None, retry=True):
    if not ensure_token(cfg):
        return 0, {}, "no token"

    code, data, raw = http_json(
        method,
        f"{panel_base(cfg)}{path}",
        headers=pasar_headers(cfg),
        payload=payload,
    )

    if code in (401, 403) and retry:
        print("Pasar token 失效或无权限，请重新登录。")
        cfg["PASAR_API_KEY"] = ""
        save_config(cfg)

        if login(cfg):
            return api(cfg, method, path, payload, retry=False)

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
