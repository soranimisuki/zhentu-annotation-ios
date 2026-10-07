# -*- coding: utf-8 -*-
import io, json, sys, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TOKEN = io.open(sys.argv[1], encoding="utf-8").read().strip()
REPO = "soranimisuki/zhentu-annotation-ios"
r = urllib.request.Request("https://api.github.com/repos/%s/releases" % REPO)
r.add_header("Authorization", "token " + TOKEN)
rel = json.loads(urllib.request.urlopen(r, timeout=60).read())
for x in rel:
    print("release:", x["tag_name"], x["name"])
    for a in x["assets"]:
        print("  asset:", a["name"], "%.1f MB" % (a["size"] / 1048576.0))
        print("  url:", a["browser_download_url"])
