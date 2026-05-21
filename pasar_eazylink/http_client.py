import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

SSL_CTX = ssl._create_unverified_context()


def http_json(method: str, url: str, headers=None, payload=None, form=None, allow_empty=False, timeout=30):
    headers = headers or {}
    data = None

    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        headers.setdefault("Content-Type", "application/json")
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    headers.setdefault("Accept", "application/json")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
            raw = resp.read().decode(errors="ignore")
            code = resp.getcode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="ignore")
        code = e.code
    except Exception as e:
        return 0, {"error": str(e)}, str(e)

    if allow_empty and not raw.strip():
        return code, {}, ""

    try:
        return code, json.loads(raw), raw
    except Exception:
        return code, {}, raw
