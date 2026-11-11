import os, re, sys, json, base64, urllib.request, urllib.parse, uuid
from concurrent.futures import ThreadPoolExecutor

MODE   = os.environ.get("MODE", "get")                    # get | split
PROTOS = os.environ.get("PROTOS", "").replace(" ", "")   # напр. "vless,hysteria2"; пусто = все
CHUNK  = int(os.environ.get("CHUNK", "1000"))             # ссылок в одном файле
TG_TOKEN, TG_CHAT = os.environ["TG_TOKEN"], os.environ["TG_CHAT_ID"]

ALL = "vless|vmess|trojan|ss|ssr|socks5?|hysteria2?|hy2|tuic|wireguard|wg|anytls|juicity|shadowtls"
LINK_RE = re.compile(rf"\b(?:{ALL})://[^\s\"'<>\\`]+", re.I)
WANT = set(PROTOS.lower().split(",")) if PROTOS else None

def fetch(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "collector"})
        return url, urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    except Exception as e:
        print("FAIL", url, e); return url, ""

def decode(text):
    if "://" in text[:3000]:
        return text
    try:
        s = re.sub(r"\s+", "", text).replace("-", "+").replace("_", "/")
        s += "=" * (-len(s) % 4)
        return base64.b64decode(s).decode("utf-8", "replace")
    except Exception:
        return text

def group_of(url):  # группа = репозиторий, чтобы /split давал файл на репозиторий
    p = urllib.parse.urlparse(url).path.strip("/").split("/")
    return p[1] if len(p) > 1 else "misc"

urls = [l.strip() for l in open("sources.txt") if l.strip() and not l.startswith("#")]
groups, seen = {}, set()
with ThreadPoolExecutor(16) as ex:
    for url, text in ex.map(fetch, urls):
        for m in LINK_RE.finditer(decode(text)):
            link = m.group(0)
            proto = link.split("://")[0].lower()
            if WANT and proto not in WANT: continue
            key = link.split("#")[0]
            if key in seen: continue
            seen.add(key)
            groups.setdefault(group_of(url), []).append(link)

def send(name, content, caption):
    b = uuid.uuid4().hex
    body = b""
    for k, v in (("chat_id", TG_CHAT), ("caption", caption)):
        body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    body += (f'--{b}\r\nContent-Disposition: form-data; name="document"; filename="{name}"\r\n'
             f'Content-Type: text/plain\r\n\r\n').encode() + content.encode() + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument", data=body,
          headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    urllib.request.urlopen(req, timeout=120).read()

def send_text(t):
    data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": t}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data).read()

total = len(seen)
if not total:
    send_text("Ничего не нашёл — источники не ответили."); sys.exit(0)

if MODE == "split":
    for g, links in groups.items():
        for i in range(0, len(links), CHUNK):
            part = links[i:i + CHUNK]
            send(f"{g}_{i // CHUNK + 1}.txt", "\n".join(part), f"{g}: {len(part)} (всего в группе {len(links)})")
else:
    flat = [l for ls in groups.values() for l in ls]
    for i in range(0, len(flat), CHUNK):
        part = flat[i:i + CHUNK]
        send(f"all_{i // CHUNK + 1}.txt", "\n".join(part), f"Часть {i // CHUNK + 1}, ссылок: {len(part)} (всего {total})")
