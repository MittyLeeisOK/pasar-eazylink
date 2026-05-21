import random
import re
import urllib.parse


def mask(value: str) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 12:
        return value
    return f"{value[:6]}...{value[-4:]}"


def input_nonempty(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("不能为空。")


def validate_username(username: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9._-]{3,64}$", username))


def validate_slug(slug: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9._-]{3,128}$", slug))


def slug_has_user_digits(slug: str, username: str) -> bool:
    if not slug.startswith(username):
        return False
    suffix = slug[len(username):]
    return bool(re.match(r"^[0-9]{4,6}$", suffix))


def suggest_slug(username: str) -> str:
    return f"{username}{random.randint(10000, 99999)}"


def prompt_slug(username: str, current: str = "") -> str:
    default = current if current else suggest_slug(username)

    while True:
        value = input(f"短链接后缀 slug [默认: {default}]: ").strip()
        slug = value or default

        if not validate_slug(slug):
            print("slug 只能包含字母、数字、点、下划线、短横线，长度 3-128。")
            continue

        if not slug_has_user_digits(slug, username):
            print(f"建议格式是：{username}+4-6位数字，例如 {suggest_slug(username)}")
            confirm = input("当前 slug 不符合建议格式，仍然使用？输入 yes 继续: ").strip()
            if confirm != "yes":
                continue

        return slug


def extract_token(value: str) -> str:
    value = value.strip()
    if not value:
        return ""

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urllib.parse.urlparse(value)
        parts = [x for x in parsed.path.split("/") if x]
        if "sub" in parts:
            idx = parts.index("sub")
            if idx + 1 < len(parts):
                return parts[idx + 1].split("?")[0].split("#")[0]
        return ""

    return value.split("?")[0].split("#")[0]


def short_token(token: str) -> str:
    if len(token) <= 16:
        return token
    return f"{token[:8]}...{token[-6:]}"


def make_long_url(token: str, cfg: dict) -> str:
    return f"{cfg['SUB_BASE_URL'].rstrip('/')}/{token}"
