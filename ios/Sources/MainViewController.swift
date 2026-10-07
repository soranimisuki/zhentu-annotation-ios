import UIKit
import WebKit
import UniformTypeIdentifiers

final class MainViewController: UIViewController,
    WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler, UIPencilInteractionDelegate {

    private var web: WKWebView!
    private var server: LocalServer?
    private var noteLabel: UILabel?
    private var watchdog: DispatchWorkItem?

    private var inboxData: Data?
    private var inboxName = "import.pdf"
    private var inboxKind = "pdf"

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = SceneDelegate.sandstone
        UIApplication.shared.isIdleTimerDisabled = true   // 批注中不锁屏

        let root = Self.webRoot()
        let srv = LocalServer(webRoot: root)
        srv.inboxProvider = { [weak self] in
            guard let self = self, let d = self.inboxData else { return nil }
            let type = self.inboxKind == "pdf" ? "application/pdf" : "application/json"
            return (d, type)
        }
        srv.exportSaver = { [weak self] data, name in
            self?.saveExport(data: data, name: name) != nil
        }
        srv.start()
        server = srv

        let cfg = WKWebViewConfiguration()
        // 构建号：页面启动时 toast 出来，用户截图即可确认装的是哪个包（排查"修复没生效"）。
        // __ZT_PRED=0：真机排障期关闭预测墨迹——桌面主文件（无预测）书写正常，先消除唯一页面差异。
        let boot = WKUserScript(
            source: "window.__ZT_SHELL=1;window.__ZT_PRED=0;window.__ZT_SHELL_BUILD='build-20261007-2300';",
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        )
        cfg.userContentController.addUserScript(boot)
        cfg.userContentController.add(self, name: "ztBridge")
        cfg.allowsInlineMediaPlayback = true

        web = WKWebView(frame: view.bounds, configuration: cfg)
        web.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        web.navigationDelegate = self
        web.uiDelegate = self
        web.isOpaque = false
        web.backgroundColor = SceneDelegate.sandstone
        web.scrollView.contentInsetAdjustmentBehavior = .never
        view.addSubview(web)

        // Apple Pencil 笔杆「轻点两下」：Safari 不转发给网页，原生壳里用 UIPencilInteraction
        // 按系统设置（设置→Apple Pencil→轻点两下）识别后转发给页面切换工具。
        let pencil = UIPencilInteraction()
        pencil.delegate = self
        web.addInteraction(pencil)

        NotificationCenter.default.addObserver(
            self, selector: #selector(flushPage),
            name: UIApplication.willResignActiveNotification, object: nil
        )

        loadApp()
    }

    static func webRoot() -> URL {
        // Web 以 folder 引用整目录进包：Bundle/<App>/Web/
        let bundled = Bundle.main.resourceURL?.appendingPathComponent("Web", isDirectory: true)
        if let bundled = bundled, FileManager.default.fileExists(atPath: bundled.appendingPathComponent("index.html").path) {
            return bundled
        }
        return Bundle.main.bundleURL.appendingPathComponent("Web", isDirectory: true)
    }

    private func loadApp() {
        hideNote()
        guard let port = server?.port, port > 0,
              let url = URL(string: "http://127.0.0.1:\(port)/index.html") else {
            note("本地服务器启动失败——点此重试")
            return
        }
        web.load(URLRequest(url: url))
        let wd = DispatchWorkItem { [weak self] in
            guard let self = self, self.web.isLoading else { return }
            self.note("加载超时——点此重试")
        }
        watchdog = wd
        DispatchQueue.main.asyncAfter(deadline: .now() + 9, execute: wd)
    }

    @objc private func flushPage() {
        web.evaluateJavaScript("try{flushSave&&flushSave()}catch(e){}", completionHandler: nil)
    }

    // MARK: - 状态提示（可点击重试）

    private func note(_ text: String) {
        watchdog?.cancel()
        let label = noteLabel ?? makeNoteLabel()
        noteLabel = label
        label.text = text + "（点按重试）"
        label.isHidden = false
    }

    private func hideNote() {
        watchdog?.cancel()
        noteLabel?.isHidden = true
    }

    private func makeNoteLabel() -> UILabel {
        let label = UILabel()
        label.frame = CGRect(x: 16, y: 80, width: view.bounds.width - 32, height: 64)
        label.autoresizingMask = [.flexibleWidth]
        label.numberOfLines = 0
        label.textAlignment = .center
        label.textColor = .white
        label.backgroundColor = UIColor(red: 0.12, green: 0.12, blue: 0.14, alpha: 0.92)
        label.layer.cornerRadius = 8
        label.layer.masksToBounds = true
        label.isUserInteractionEnabled = true
        label.isHidden = true
        label.font = .systemFont(ofSize: 14)
        view.addSubview(label)
        label.addGestureRecognizer(UITapGestureRecognizer(target: self, action: #selector(noteTapped)))
        return label
    }

    @objc private func noteTapped() {
        loadApp()
    }

    // MARK: - WKNavigationDelegate（让错误可见：SKILL.md §4.6）

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        hideNote()
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        note("页面出错：" + error.localizedDescription)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        note("加载失败：" + error.localizedDescription)
    }

    func webView(
        _ webView: WKWebView,
        createWebViewWith configuration: WKWebViewConfiguration,
        for navigationAction: WKNavigationAction,
        windowFeatures: WKWindowFeatures
    ) -> WKWebView? {
        if navigationAction.targetFrame == nil {
            webView.load(navigationAction.request)
        }
        return nil
    }

    // MARK: - WKUIDelegate：alert/confirm/prompt 必须自建（SKILL.md §4.3）

    func webView(
        _ webView: WKWebView,
        runJavaScriptAlertPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping () -> Void
    ) {
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "好", style: .default) { _ in completionHandler() })
        presentSheet(alert, tag: "alert")
    }

    func webView(
        _ webView: WKWebView,
        runJavaScriptConfirmPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping (Bool) -> Void
    ) {
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "确定", style: .default) { _ in completionHandler(true) })
        alert.addAction(UIAlertAction(title: "取消", style: .cancel) { _ in completionHandler(false) })
        presentSheet(alert, tag: "confirm")
    }

    func webView(
        _ webView: WKWebView,
        runJavaScriptTextInputPanelWithPrompt prompt: String,
        defaultText: String?,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping (String?) -> Void
    ) {
        let alert = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
        alert.addTextField { $0.text = defaultText }
        alert.addAction(UIAlertAction(title: "确定", style: .default) { _ in
            completionHandler(alert.textFields?.first?.text)
        })
        alert.addAction(UIAlertAction(title: "取消", style: .cancel) { _ in completionHandler(nil) })
        presentSheet(alert, tag: "prompt")
    }

    @discardableResult
    private func presentSheet(_ vc: UIViewController, tag: String) -> Bool {
        if vc.popoverPresentationController != nil {
            vc.popoverPresentationController?.sourceView = view
            vc.popoverPresentationController?.sourceRect = CGRect(
                x: view.bounds.midX, y: view.bounds.midY, width: 1, height: 1
            )
        }
        if presentedViewController != nil {
            dismiss(animated: true) { [weak self] in
                _ = self?.presentSheet(vc, tag: tag)
            }
            return true
        }
        present(vc, animated: true)
        return true
    }

    // MARK: - Apple Pencil 轻点两下

    func pencilInteraction(_ interaction: UIPencilInteraction, didReceiveTap tap: UIPencilInteraction.Tap) {
        let pref = UIPencilInteraction.preferredTapAction
        var name: String
        switch pref {
        case .switchEraser: name = "switchEraser"
        case .switchPrevious: name = "switchPrevious"
        case .showColorPalette: name = "colorPalette"
        case .showInkAttributes: name = "inkAttributes"
        case .ignore: return
        @unknown default: return
        }
        web.evaluateJavaScript(
            "window.__ztPencilTap&&window.__ztPencilTap('\(name)')",
            completionHandler: nil
        )
    }

    // MARK: - JS 桥：导入 / 导出

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "ztBridge",
              let body = message.body as? [String: Any],
              let type = body["type"] as? String else { return }
        switch type {
        case "import":
            presentImport(kind: body["kind"] as? String ?? "pdf")
        case "exported":
            presentExport(name: body["name"] as? String ?? "")
        default:
            break
        }
    }

    private func presentImport(kind: String) {
        let isJSON = (kind == "bak" || kind == "vocab")
        let types: [UTType] = isJSON ? [.json] : [.pdf]
        inboxKind = kind
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: types, asCopy: true)
        picker.allowsMultipleSelection = false
        picker.delegate = self
        presentSheet(picker, tag: "import")
    }

    private func deliverInbox() {
        guard inboxData != nil else { return }
        let script = "window.__ztShellFile&&window.__ztShellFile('/__zt/inbox?t='+Date.now(),"
            + Self.jsString(inboxName) + "," + Self.jsString(inboxKind) + ")"
        web.evaluateJavaScript(script, completionHandler: nil)
    }

    private func saveExport(data: Data, name: String) -> URL? {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
        guard let dir = docs?.appendingPathComponent("exports", isDirectory: true) else { return nil }
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let safe = LocalServer.sanitizeFilename(name)
        // 主名写失败（异常字符/占用等）→ 回退到时间戳名再试一次
        let ext = (safe as NSString).pathExtension
        let fallback = "export-" + String(Int(Date().timeIntervalSince1970)) + (ext.isEmpty ? "" : "." + ext)
        for fn in [safe, fallback] {
            let url = dir.appendingPathComponent(fn)
            do {
                try data.write(to: url, options: .atomic)
                return url
            } catch {
                continue
            }
        }
        return nil
    }

    private func presentExport(name: String) {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
        guard let dir = docs?.appendingPathComponent("exports", isDirectory: true) else { return }
        let url = dir.appendingPathComponent(LocalServer.sanitizeFilename(name))
        guard FileManager.default.fileExists(atPath: url.path) else {
            note("导出文件不存在：" + name)
            return
        }
        let sheet = UIActivityViewController(activityItems: [url], applicationActivities: nil)
        presentSheet(sheet, tag: "export")
    }

    static func jsString(_ s: String) -> String {
        var t = s.replacingOccurrences(of: "\\", with: "\\\\")
        t = t.replacingOccurrences(of: "'", with: "\\'")
        t = t.replacingOccurrences(of: "\"", with: "\\\"")
        t = t.replacingOccurrences(of: "\n", with: "\\n")
        t = t.replacingOccurrences(of: "\r", with: "\\r")
        return "'" + t + "'"
    }
}

extension MainViewController: UIDocumentPickerDelegate {

    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        guard let url = urls.first else { return }
        guard let data = try? Data(contentsOf: url) else {
            note("读取文件失败")
            return
        }
        inboxData = data
        inboxName = LocalServer.sanitizeFilename(url.lastPathComponent)
        deliverInbox()
    }
}
