# 真题手写批注 · iOS App（未签名 IPA）

把 `D:\考研\英语\真题手写批注\index.html`（单文件手写批注阅读站）打包成 iPad/iPhone 原生 App：
WKWebView 壳 + 本地 HTTP 服务器 + **Apple Pencil 笔杆双击切换工具**（原生 `UIPencilInteraction`）+ 书写顺滑化增强。
走 GitHub Actions macOS 云编译，Windows 上无需 Mac 即可出可侧载的未签名 IPA。

## 架构

```
webapp/index.html      页面副本（由 tools/sync_webapp.py 从主 index.html 幂等打补丁生成）
webapp/vendor/         pdf.js 3.11.174 + pdf-lib 1.17.1 本地副本（App 内完全离线渲染/导出）
ios/project.yml        xcodegen 工程定义（唯一手写工程文件，锁 Xcode 15.4 工程格式）
ios/Sources/           Swift 壳（约 600 行，无第三方依赖）
  AppDelegate.swift      @main + Scene 生命周期（iPadOS 26 缺它启动即崩）
  SceneDelegate.swift    UIWindow(windowScene:)
  MainViewController.swift  WKWebView + alert/confirm/prompt 面板 + UIPencilInteraction + 导入导出桥
  LocalServer.swift      Network.framework 手写 HTTP/1.1（127.0.0.1 固定端口，keep-alive）
ios/Web/               CI 时由 webapp/ 拷入（folder 引用整目录进包）
```

## 为什么有本地服务器

页面的批注/生词/偏好全部存 **localStorage**，而 WKWebView 走 `file://` 时 localStorage/IndexedDB
不可靠。App 内起 `http://127.0.0.1:<固定端口>/`，数据落在持久的 origin 上。端口优先用上次启动
记住的值（UserDefaults），保证跨启动 origin 一致——**数据不因换端口而"消失"**。

## Apple Pencil 笔杆双击

Safari 不把「轻点两下」转发给网页，App 里用 `UIPencilInteraction` 按**系统设置 → Apple Pencil →
轻点两下**识别后转发给页面：

| 系统设置 | App 内行为 |
|---|---|
| 切换到橡皮（默认） | 书写 ↔ 橡皮 |
| 切换到上次使用的工具 | 书写 ↔ 上一个书写类工具（荧光等） |
| 显示调色板 / 显示墨水属性 | 提示未映射 |
| 关闭 | 不响应 |

页面侧原有的三层兜底（笔尖快速两下自研检测 / dblclick 兜底 / 右下角悬浮快切按钮）全部保留。

## 书写顺滑化（相对网页版）

1. **预测墨迹**：`getPredictedEvents()`（iOS 18.2+）把系统预测的未来轨迹画成"湿墨尾巴"，
   每个真实采样点到来即整体替换；停笔由过期定时器擦除，不进数据。视觉上追回约一帧延迟。
2. **性能修复（2026-10-07）**：收笔改增量叠底图（不再每笔整页重描）、落盘推迟到手离开屏幕、
   多选移动/缩放手势改快照渲染（不再每个触摸事件整页重建）——两笔之间与多选手势不再卡顿。
3. 子帧采样（`getCoalescedEvents`）、变量宽度带状填充、rAF 合帧、底图缓存为网页版已有，保持不变。

## 导入 / 导出（原生桥）

- 导入 PDF / 生词 JSON / 备份 JSON：`UIDocumentPickerViewController` → 内存 inbox →
  页面 `fetch('/__zt/inbox')` 取回构造 File，走原有导入逻辑（也支持"文件"App 里分享/打开方式）。
- 导出批注 PDF / 生词表 / 备份 JSON：页面 `POST /__zt/export?name=…` → 落到
  App 沙盒 `Documents/exports/` → 弹**系统分享面板**（存到"文件"、AirDrop、打印…）。
- 大数据不走 JS 桥字符串（几 MB JSON/二进制全走 localhost HTTP）。

## CI（GitHub Actions）

`.github/workflows/ios-ipa.yml`：macos runner → xcodegen 生成工程 → `xcodebuild` arm64 未签名 →
IPA 挂到 **Releases（tag `v1.0-ipa`）**，同时传 Actions artifact。
推送 `webapp/**`、`ios/**` 或 workflow 本身即触发；也可手动 workflow_dispatch。

改页面后的发布流程：

```bash
python tools/sync_webapp.py     # 从 ../index.html 重新生成 webapp/index.html（幂等，锚点断言）
node tools/check_page_js.mjs webapp/index.html   # 内联 JS 语法检查
python "技能目录/scripts/check_swift.py" ios/Sources/*.swift   # Swift 结构自检
# git 提交推送（本机无 git 时可用 tools/push_github.py 走 GitHub API）
```

## 侧载（用户侧）

Sideloadly（Windows）/ AltStore / 爱思助手，导入 Releases 里的 `app-unsigned.ipa` 自签安装。
免费 Apple ID 签名 7 天过期需重签；覆盖安装用同一 bundle id + 同一 Apple ID 数据不丢。

## 数据迁移（网页版 → App）

网页版（Safari 局域网访问）的批注存在 Safari 的 localStorage，与 App 的 origin 不同，App 里看不到。
迁移：网页版 →「⋯ → 备份全部数据」导出 JSON → App 内「⋯ → 恢复备份」导入。

## 本地验证工具（tools/）

| 文件 | 作用 |
|---|---|
| `sync_webapp.py` | 主 index.html → webapp/index.html 幂等补丁器（18 处锚点断言） |
| `check_page_js.mjs` | 提取内联 `<script>` 逐块语法检查 |
| `cdp_probe.mjs` | 无头 Chrome CDP 探针（selftest + 任意 JS 表达式注入） |
| `probe_ink2.json` | 合成 Apple Pencil 事件全链路：预测捕获/过期/收笔落库/撤销 |
| `probe_shell.json` | 壳内导出分支验证（?shelltest=1 + 真实点击导出按钮） |
| `gen_icon.py` | 生成 1024 App 图标（PIL，砂岩+墨迹+信号黄） |
| `push_github.py` | 本机无 git 时的 GitHub API 推送（token 只从环境变量读） |
