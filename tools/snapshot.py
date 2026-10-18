"""Snapshot the favorites of a wall: their data + a small local picture, so the Favorites room hangs at once.

Usage:  python3 tools/snapshot.py "<share link>"      (run from the repo root; serves the repo on :8766 itself)
Writes: snapshot.json and assets/snap/<id>.webp|.svg. Re-run after the favorites change, then commit and push.
"""
import base64, hashlib, io, json, os, re, subprocess, sys, time, urllib.request
from datetime import datetime, timezone
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPDIR = os.path.join(ROOT, "assets", "snap")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
GATEWAYS = ["https://ipfs.filebase.io/ipfs/", "https://ipfs.io/ipfs/", "https://dweb.link/ipfs/", "https://gateway.pinata.cloud/ipfs/", "https://4everland.io/ipfs/"]

def candidates(u):
    if not u: return []
    if u.startswith("data:") or u.startswith("assets/"): return [u]
    if u.startswith("ar://"): return ["https://arweave.net/" + u[5:]]
    m = re.search(r"(?:ipfs://|/ipfs/)(?:ipfs/)?(.+)$", u)
    out = [g + m.group(1) for g in GATEWAYS] if m else []
    if u.startswith("http"): out.append(u.replace("http://", "https://", 1))
    return out

def fetch(u):
    if u.startswith("data:"):
        head, _, body = u.partition(",")
        return base64.b64decode(body) if ";base64" in head else urllib.parse.unquote_to_bytes(body)
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60).read()

def save_picture(key, urls):
    name = hashlib.sha1(key.encode()).hexdigest()[:16]
    for u in urls:
        try: data = fetch(u)
        except Exception: continue
        if len(data) < 200: continue
        if data.lstrip()[:5] in (b"<svg ", b"<?xml") or b"<svg" in data[:300]:
            if len(data) > 600_000: continue
            path = os.path.join(SNAPDIR, name + ".svg"); open(path, "wb").write(data); return "assets/snap/" + name + ".svg"
        try:
            im = Image.open(io.BytesIO(data)); im.seek(0); im = im.convert("RGBA")
            im.thumbnail((720, 720))
            path = os.path.join(SNAPDIR, name + ".webp"); im.save(path, "WEBP", quality=82, method=6)
            return "assets/snap/" + name + ".webp"
        except Exception: continue
    return None

def main(link):
    import urllib.parse  # noqa: F401  (used by fetch for data: URIs)
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8766"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    url = "http://localhost:8766/" + link[link.index("#"):]
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(user_agent=UA, viewport={"width": 1440, "height": 1000})
            pg.goto(url); pg.wait_for_timeout(3000)
            t = time.time()
            while time.time() - t < 400 and (not pg.query_selector_all(".piece") or pg.inner_text("#status") != ""): time.sleep(2)
            favs = pg.evaluate("window.__nftwallFavs()")
            pg.evaluate("document.querySelector('#rooms button[data-v=fav]').click()"); pg.wait_for_timeout(1500)
            for _ in range(3):                                   # scroll every favorite into view so its picture loads
                n = pg.evaluate("document.querySelectorAll('.piece').length")
                for i in range(n):
                    pg.evaluate("i => { const e = document.querySelectorAll('.piece')[i]; if (e) e.scrollIntoView({block: 'center'}); }", i)
                    pg.wait_for_timeout(300)
                t = time.time()
                while time.time() - t < 120 and pg.evaluate("window.__nftwallBusy()"): time.sleep(2)
                pg.wait_for_timeout(8000)
            rows = pg.evaluate("k => window.__nftwallExport(k)", favs)
            b.close()
    finally:
        srv.terminate()
    os.makedirs(SNAPDIR, exist_ok=True)
    for f in os.listdir(SNAPDIR): os.remove(os.path.join(SNAPDIR, f))   # rebuild: no stale pictures
    items, got = {}, 0
    for r in rows:
        it = r["item"]; md = it.get("metadata") or {}
        thumb = md.get("image") if str(md.get("image") or "").startswith("assets/") else save_picture(r["key"], ([r["src"]] if r["src"] else []) + candidates(md.get("image")))
        it["thumb"] = thumb; items[r["key"]] = it; got += bool(thumb)
        print(("ok   " if thumb else "NONE ") + r["key"][:60], "|", (md.get("name") or "")[:40])
    json.dump({"v": 1, "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "items": items},
              open(os.path.join(ROOT, "snapshot.json"), "w"), separators=(",", ":"))
    size = sum(os.path.getsize(os.path.join(SNAPDIR, f)) for f in os.listdir(SNAPDIR))
    print(f"\n{len(items)} favorites, {got} with a local picture, {size // 1024} KB of pictures -> snapshot.json")

if __name__ == "__main__":
    main(sys.argv[1])
