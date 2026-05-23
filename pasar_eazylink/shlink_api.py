import urllib.parse

from .http_client import http_json


def headers(cfg: dict) -> dict:
    return {
        "X-Api-Key": cfg.get("SHLINK_API_KEY", ""),
    }


def ensure_key(cfg: dict) -> bool:
    if cfg.get("SHLINK_API_KEY"):
        return True
    print("Shlink API Key 为空，请先到 设置 -> Shlink API Key。")
    return False


def api(cfg: dict, method: str, path: str, payload=None, allow_empty=False):
    if not ensure_key(cfg):
        return 0, {}, "no shlink key"

    return http_json(
        method,
        f"{cfg['SHLINK_API_BASE'].rstrip('/')}{path}",
        headers=headers(cfg),
        payload=payload,
        allow_empty=allow_empty,
    )


def item_code(item: dict) -> str:
    return item.get("shortCode") or item.get("short_code") or ""


def item_long_url(item: dict) -> str:
    return item.get("longUrl") or item.get("long_url") or ""


def item_short_url(item: dict, cfg: dict) -> str:
    return item.get("shortUrl") or f"{cfg['SHORT_DOMAIN'].rstrip('/')}/{item_code(item)}"


def list_all(cfg: dict) -> list[dict]:
    if not ensure_key(cfg):
        return []

    all_items = []
    page = 1

    while True:
        code, data, raw = api(cfg, "GET", f"/short-urls?itemsPerPage=100&page={page}")

        if code != 200:
            print(f"读取短链接失败，HTTP {code}")
            if raw:
                print(raw)
            return []

        block = data.get("shortUrls", data)
        if isinstance(block, dict):
            items = block.get("data", data.get("data", []))
            pagination = block.get("pagination", data.get("pagination", {}))
        else:
            items = []
            pagination = {}

        all_items.extend(items)

        pages = int(pagination.get("pagesCount") or pagination.get("pages") or page)
        if page >= pages:
            break

        page += 1

    return all_items


def filtered(cfg: dict, query: str = "") -> list[dict]:
    q = query.lower().strip()
    items = list_all(cfg)
    out = []

    for item in items:
        text = f"{item_code(item)} {item_short_url(item, cfg)} {item_long_url(item)}".lower()
        if q and q not in text:
            continue
        out.append(item)

    return out


def show_list(cfg: dict, query: str = "") -> list[dict]:
    items = filtered(cfg, query)

    print()
    print("=== Shlink 短链接列表 ===")
    print("序号\tshortCode\t短链接\t目标")

    for i, item in enumerate(items, 1):
        print(f"{i}\t{item_code(item)}\t{item_short_url(item, cfg)}\t{item_long_url(item)}")

    if not items:
        print("无匹配短链接")

    print()
    return items


def create(cfg: dict, slug: str, long_url: str):
    payload = {
        "longUrl": long_url,
        "customSlug": slug,
        "findIfExists": False,
    }
    return api(cfg, "POST", "/short-urls", payload)


def patch(cfg: dict, short_code: str, long_url: str):
    payload = {
        "longUrl": long_url,
    }
    return api(cfg, "PATCH", f"/short-urls/{urllib.parse.quote(short_code)}", payload)


def delete(cfg: dict, short_code: str):
    return api(
        cfg,
        "DELETE",
        f"/short-urls/{urllib.parse.quote(short_code)}",
        allow_empty=True,
    )


def upsert(cfg: dict, slug: str, long_url: str) -> bool:
    code, data, raw = create(cfg, slug, long_url)

    if code in (200, 201):
        print(f"短链接已新建：{data.get('shortUrl') or cfg['SHORT_DOMAIN'].rstrip('/') + '/' + slug}")
        return True

    code2, data2, raw2 = patch(cfg, slug, long_url)

    if 200 <= code2 < 300:
        print(f"短链接已覆盖：{data2.get('shortUrl') or cfg['SHORT_DOMAIN'].rstrip('/') + '/' + slug}")
        return True

    print(f"短链接创建/覆盖失败。POST HTTP {code}，PATCH HTTP {code2}")
    if raw:
        print(raw)
    if raw2:
        print(raw2)

    return False


def select(cfg: dict, query_prompt=True):
    query = input("输入用户名/关键词搜索，留空列出全部: ").strip() if query_prompt else ""
    items = show_list(cfg, query)

    if not items:
        return None

    while True:
        value = input("选择序号，或输入 0 取消: ").strip()

        if value == "0":
            return None

        if value.isdigit() and 1 <= int(value) <= len(items):
            return items[int(value) - 1]

        print("序号无效。")


def test_api(cfg: dict):
    code, data, raw = api(cfg, "GET", "/short-urls?itemsPerPage=1")
    print(f"HTTP {code}")

    if data:
        import json
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(raw)
