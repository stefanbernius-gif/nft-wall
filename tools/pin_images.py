"""Pin the IPFS images of one wallet's NFTs to Stefan's Pinata account (pinByHash), so the
nft-museum.mypinata.cloud gateway can serve them and they stay alive.
Input: .tmp/ipfs-refs.json (built from .tmp/my-nfts.json). Keys: .env (PINATA_JWT). Never prints secrets.
Folder CIDs that hold a whole collection (many files) are skipped: pinning them would store the entire collection."""
import json, os, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = dict(l.strip().split("=", 1) for l in open(os.path.join(ROOT, ".env")) if "=" in l and not l.startswith("#"))
JWT = env["PINATA_JWT"]
SKIP_ROOTS = set(sys.argv[1:])            # e.g. the OptiNouns collection folder

def api(method, path, body=None):
    req = urllib.request.Request("https://api.pinata.cloud" + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + JWT, "Content-Type": "application/json", "User-Agent": "nft-wall/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, e.read().decode()[:200]

refs = json.load(open(os.path.join(ROOT, ".tmp/ipfs-refs.json")))
done = set()
for r in refs:
    cid = r["cid"]
    if cid in done or cid in SKIP_ROOTS: continue
    done.add(cid)
    name = ("nft-wall: " + r["nfts"][0])[:100]
    code, res = api("POST", "/pinning/pinByHash", {"hashToPin": cid, "pinataMetadata": {"name": name}})
    print(code, cid[:20], name[:60], "" if code == 200 else res)
