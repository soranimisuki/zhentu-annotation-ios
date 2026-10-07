# -*- coding: utf-8 -*-
"""盯 GitHub Actions run：轮询最新 run，完成后打印结论；失败时下载日志提取 error 行。"""
import io, os, sys, time, json, zipfile, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = "soranimisuki/zhentu-annotation-ios"
TOKEN = io.open(sys.argv[1], encoding="utf-8").read().strip()


def req(path, raw=False, method="GET"):
    r = urllib.request.Request("https://api.github.com" + path, method=method)
    r.add_header("Authorization", "token " + TOKEN)
    r.add_header("Accept", "application/vnd.github+json")
    r.add_header("User-Agent", "watch_ci.py")
    with urllib.request.urlopen(r, timeout=60) as resp:
        return resp.read()


run_id = None
for i in range(60):
    runs = json.loads(req("/repos/%s/actions/runs?per_page=3" % REPO))
    if runs.get("workflow_runs"):
        run = runs["workflow_runs"][0]
        if run["head_sha"] and run["status"]:
            rid = run["id"]
            if run_id != rid:
                run_id = rid
                print("run %d: %s (%s) created %s" % (rid, run["status"], run.get("conclusion"), run["created_at"]))
            if run["status"] == "completed":
                print("CONCLUSION:", run["conclusion"])
                if run["conclusion"] != "success":
                    z = req("/repos/%s/actions/runs/%d/logs" % (REPO, rid))
                    p = os.path.join(os.environ["TEMP"], "zt_ci_logs.zip")
                    io.open(p, "wb").write(z)
                    with zipfile.ZipFile(p) as zf:
                        for nm in zf.namelist():
                            if "xcodebuild" in nm or ("build" in nm and nm.endswith(".txt")):
                                txt = zf.read(nm).decode("utf-8", "replace")
                                errs = [l for l in txt.splitlines() if "error:" in l]
                                if errs:
                                    print("== %s ==" % nm)
                                    for l in errs[:30]:
                                        print("   ", l[:220])
                        # 兜底：所有日志里找 error:
                        if True:
                            seen = set()
                            for nm in zf.namelist():
                                try:
                                    txt = zf.read(nm).decode("utf-8", "replace")
                                except Exception:
                                    continue
                                for l in txt.splitlines():
                                    if "error:" in l and l not in seen:
                                        seen.add(l)
                                        print("   [%s] %s" % (nm, l[:220]))
                                        if len(seen) > 40:
                                            break
                sys.exit(0)
    else:
        print("no runs yet...")
    time.sleep(20)
print("timeout waiting for CI")
sys.exit(1)
