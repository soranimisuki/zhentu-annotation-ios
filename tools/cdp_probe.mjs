// 无头 Chrome CDP 探针：spawn chrome(--remote-debugging-port=0) → 连 browser ws →
// 开标签加载 URL → 等 selftest 输出 → 执行注入的 JS 表达式并打印结果。
// 用法：node cdp_probe.mjs <url> [表达式文件]
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const url = process.argv[2];
const exprFile = process.argv[3] || "";

function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const prof = fs.mkdtempSync(path.join(os.tmpdir(), "zt_cdp_"));
  const chrome = spawn(CHROME, [
    "--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    `--user-data-dir=${prof}`, "--remote-debugging-port=0", "about:blank",
  ], { stdio: ["ignore", "ignore", "pipe"] });

  let wsBase = null;
  const stderr = "";
  chrome.stderr.on("data", d => {
    const s = d.toString();
    const m = s.match(/DevTools listening on (ws:\/\/\S+)/);
    if (m) wsBase = m[1];
  });
  for (let i = 0; i < 100 && !wsBase; i++) await wait(100);
  if (!wsBase) { console.error("chrome devtools endpoint not found", stderr); process.exit(2); }

  // browser 级 ws
  const ws = new WebSocket(wsBase);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let mid = 0;
  const pending = new Map();
  const events = [];
  ws.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
    else if (msg.method) events.push(msg);
  };
  const send = (method, params = {}, sessionId) => new Promise(res => {
    const id = ++mid;
    pending.set(id, res);
    ws.send(JSON.stringify(sessionId ? { id, method, params, sessionId } : { id, method, params }));
  });

  const created = await send("Target.createTarget", { url });
  const targetId = created.result.targetId;
  const attached = await send("Target.attachToTarget", { targetId, flatten: true });
  const sid = attached.result.sessionId;
  await send("Page.enable", {}, sid);

  // 等 load + selftest pre 出现（selftest 在 600ms 后跑）
  let selftestText = "";
  for (let i = 0; i < 150; i++) {
    await wait(200);
    const r = await send("Runtime.evaluate", {
      expression: `(() => { const p=[...document.querySelectorAll('pre')].map(x=>x.textContent).find(t=>t&&t.indexOf('selftest')===0); return p||''; })()`,
      returnByValue: true,
    }, sid);
    if (r.result && r.result.result && r.result.result.value) { selftestText = r.result.result.value; break; }
  }
  if (selftestText) console.log("---- selftest ----\n" + selftestText + "\n---- verdict: " + (selftestText.includes("ALL PASS") ? "ALL PASS" : "HAS FAIL"));

  if (exprFile) {
    const exprs = JSON.parse(fs.readFileSync(exprFile, "utf8"));
    for (const e of exprs) {
      const r = await send("Runtime.evaluate", { expression: e.expr, returnByValue: true, awaitPromise: !!e.awaitPromise }, sid);
      if (r.result && r.result.exceptionDetails) {
        const ex = r.result.exceptionDetails;
        console.log("PROBE " + e.name + " => EXCEPTION " + ((ex.exception && ex.exception.description) || ex.text));
        continue;
      }
      const v = r.result && r.result.result ? r.result.result.value : JSON.stringify(r.result);
      console.log("PROBE " + e.name + " => " + JSON.stringify(v));
      if (e.waitMs) await wait(e.waitMs);
    }
  }
  chrome.kill();
  process.exit(0);
}

main().catch(e => { console.error("probe error:", e); process.exit(1); });
