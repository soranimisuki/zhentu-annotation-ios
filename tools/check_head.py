# -*- coding: utf-8 -*-
import io, json, sys, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TOKEN = io.open(sys.argv[1], encoding="utf-8").read().strip()
REPO = "soranimisuki/zhentu-annotation-ios"
r = urllib.request.Request("https://api.github.com/repos/%s/commits?per_page=3" % REPO)
r.add_header("Authorization", "token " + TOKEN)
for c in json.loads(urllib.request.urlopen(r, timeout=60).read()):
    print(c["sha"][:10], c["commit"]["message"].splitlines()[0][:80])
