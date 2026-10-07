# -*- coding: utf-8 -*-
"""本机无 git 时的 GitHub 推送：Git Data API（blobs → tree → commit → ref）。
全程只走 api.github.com（github.com 直连不通的环境可用，见 ios-ipa-cloud-build 技能 §7）。

用法：
  set GITHUB_TOKEN=ghp_xxx
  python push_github.py owner/repo [branch]

token 只从环境变量或 --token-file 读，绝不写入本文件/仓库。
"""
import argparse, base64, io, json, os, subprocess, sys, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
API = "https://api.github.com"


def http(method, path, token, payload=None, raw=False):
    url = API + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "token " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "push_github.py")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            return r.status, (body if raw else (json.loads(body) if body else {}))
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body.decode("utf-8", "replace")[:400]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")            # owner/name
    ap.add_argument("--branch", default="main")
    ap.add_argument("--token-file", default=None)
    ap.add_argument("--message", default="update")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token and args.token_file:
        token = io.open(args.token_file, encoding="utf-8").read().strip()
    if not token:
        sys.exit("需要 GITHUB_TOKEN 环境变量或 --token-file")

    owner, name = args.repo.split("/")
    files = []
    for root, dirs, fnames in os.walk("."):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for fn in fnames:
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, ".").replace("\\", "/")
            if rel.startswith("_tmp") or "/_tmp" in rel:
                continue
            files.append(rel)
    files.sort()
    print("files: %d" % len(files))
    for f in files:
        print("  ", f)

    # 仓库不存在则创建（公开仓库：macOS runner 免费）
    st, _ = http("GET", "/repos/%s/%s" % (owner, name), token)
    if st == 404:
        st, r = http("POST", "/user/repos", token, {
            "name": name,
            "description": "真题手写批注 iOS（WKWebView 壳 + Apple Pencil 双击切换 + 预测墨迹）",
            "private": False,
            "has_wiki": False,
        })
        print("create repo:", st)
        if st >= 300:
            sys.exit(json.dumps(r, ensure_ascii=False)[:600])

    # 基准 commit / tree
    st, ref = http("GET", "/repos/%s/%s/git/ref/heads/%s" % (owner, name, args.branch), token)
    base_commit = ref.get("object", {}).get("sha") if st == 200 else None

    # 空仓库上 git/blobs 会 409（Git Repository is empty）：先用 contents API 播种一个首提交
    if base_commit is None:
        st2, empty = http("GET", "/repos/%s/%s/contents" % (owner, name), token)
        if st2 == 404 or (st2 == 200 and empty == []):
            st3, seed = http("PUT", "/repos/%s/%s/contents/README.md" % (owner, name), token, {
                "message": "init",
                "content": base64.b64encode(io.open("README.md", "rb").read()).decode("ascii"),
            })
            print("seed empty repo:", st3)
            if st3 >= 300:
                sys.exit(json.dumps(seed, ensure_ascii=False)[:600])
            st, ref = http("GET", "/repos/%s/%s/git/ref/heads/%s" % (owner, name, args.branch), token)
            base_commit = ref.get("object", {}).get("sha")

    base_tree = None
    if base_commit:
        st, c = http("GET", "/repos/%s/%s/git/commits/%s" % (owner, name, base_commit), token)
        base_tree = c["tree"]["sha"]
        print("base commit:", base_commit[:10])

    # blobs
    tree = []
    for rel in files:
        blob = io.open(rel, "rb").read()
        if rel.lower().endswith((".png", ".jpg", ".ico")):
            enc, content = "base64", base64.b64encode(blob).decode("ascii")
        else:
            enc, content = "utf-8", blob.decode("utf-8")
        st, b = http("POST", "/repos/%s/%s/git/blobs" % (owner, name), token,
                     {"content": content, "encoding": enc})
        if st >= 300:
            sys.exit("blob fail %s: %s %s" % (rel, st, json.dumps(b)[:300]))
        tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": b["sha"]})
        print("  blob", rel, b["sha"][:8])

    st, t = http("POST", "/repos/%s/%s/git/trees" % (owner, name), token,
                 {"base_tree": base_tree, "tree": tree})
    if st >= 300:
        sys.exit("tree fail: %s %s" % (st, json.dumps(t)[:400]))
    print("tree:", t["sha"][:10])

    payload = {"message": args.message, "tree": t["sha"],
               "parents": [base_commit] if base_commit else []}
    st, c = http("POST", "/repos/%s/%s/git/commits" % (owner, name), token, payload)
    if st >= 300:
        sys.exit("commit fail: %s %s" % (st, json.dumps(c)[:400]))
    print("commit:", c["sha"][:10])

    if base_commit:
        st, r = http("PATCH", "/repos/%s/%s/git/refs/heads/%s" % (owner, name, args.branch), token,
                     {"sha": c["sha"], "force": False})
    else:
        st, r = http("POST", "/repos/%s/%s/git/refs" % (owner, name), token,
                     {"ref": "refs/heads/%s" % args.branch, "sha": c["sha"]})
    if st >= 300:
        sys.exit("ref fail: %s %s" % (st, json.dumps(r)[:400]))
    print("pushed -> %s/%s@%s" % (owner, name, args.branch))
    print("https://github.com/%s/%s/actions" % (owner, name))


if __name__ == "__main__":
    main()
