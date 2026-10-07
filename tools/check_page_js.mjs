// 提取 HTML 内联 <script> 并逐块 node --check（spawn 自身用 --check 参数太绕，直接 new Function 编译验证）
import fs from "node:fs";
import vm from "node:vm";

const file = process.argv[2];
const html = fs.readFileSync(file, "utf8");
const re = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi;
let m, i = 0, fail = 0;
while ((m = re.exec(html)) !== null) {
  i++;
  const code = m[1];
  if (!code.trim()) continue;
  try {
    new vm.Script(code, { filename: `inline-${i}.js` });
    console.log(`script #${i}: OK (${code.length} chars)`);
  } catch (e) {
    fail++;
    console.error(`script #${i}: FAIL ${e.message}`);
    const line = e.stack.split("\n")[0] || "";
    console.error(line);
  }
}
console.log(fail === 0 ? "ALL PASS" : `${fail} FAIL`);
process.exit(fail === 0 ? 0 : 1);
