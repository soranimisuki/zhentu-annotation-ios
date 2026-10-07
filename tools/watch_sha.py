# -*- coding: utf-8 -*-
"""按 head SHA 精确盯 CI：python watch_sha.py <token> <sha_prefix>"""
import io, json, os, sys, time, zipfile, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = "soranimisuki/zhentu-annotation-ios"
TOKEN = io.open(sys.argv[1], encoding="utf-8").read().strip()
SHA = sys.argv[2]


def req(path):
    r = urllib.request.Request("https://api.github.com" + path)
    r.add_header("Authorization", "token " + TOKEN)
    r.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(r, timeout=60) as resp:
        return resp.read()


for i in range(90):
    runs = json.loads(req("/repos/%s/actions/runs?per_page=5" % REPO))
    hit = None
    for run in runs.get("workflow_runs", []):
        if run["head_sha"].startswith(SHA):
            hit = run
            break
    if hit:
        print("run %d sha %s: %s" % (hit["id"], hit["head_sha"][:8], hit["status"]))
        if hit["status"] == "completed":
            print("CONCLUSION:", hit["conclusion"])
            if hit["conclusion"] != "success":
                z = req("/repos/%s/actions/runs/%d/logs" % (REPO, hit["id"]))
                p = os.path.join(os.environ["TEMP"], "zt_ci_logs2.zip")
                io.open(p, "wb").write(z)
                seen = set()
                with zipfile.ZipFile(p) as zf:
                    for nm in zf.namelist():
                        try:
                            txt = zf.read(nm).decode("utf-8", "replace")
                        except Exception:
                            continue
                        for l in txt.splitlines():
                            if "error:" in l and l not in seen:
                                seen.add(l)
                                print("   ", l[:220])
                                if len(seen) > 30:
                                    break
            sys.exit(0)
    else:
        print("waiting for run of", SHA[:8], "...")
    time.sleep(20)
print("timeout")
sys.exit(1)
