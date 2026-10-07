import Foundation
import Network

/// 本地静态服务器：绑 127.0.0.1，给 WKWebView 提供 http://127.0.0.1:<port>/ 起源。
/// 页面的批注/生词/偏好全存 localStorage——origin 里含端口，所以跨启动端口必须一致：
/// 先用上次记住的端口，再按固定候选表尝试，最后才回退随机端口（数据 origin 会变，属兜底）。
/// 动态路由：
///   GET  /__zt/inbox          -> 原生导入的 PDF/JSON（由 InboxProvider 提供）
///   POST /__zt/export?name=x  -> 页面 POST 导出文件，交给 ExportSaver 落盘
final class LocalServer: NSObject {

    var inboxProvider: (() -> (Data, String)?)?
    var exportSaver: ((_ data: Data, _ name: String) -> Bool)?

    private(set) var port: UInt16 = 0
    private var listener: NWListener?
    private let webRoot: URL
    private let queue = DispatchQueue(label: "zt.localserver")

    init(webRoot: URL) {
        self.webRoot = webRoot
        super.init()
    }

    func start() {
        var candidates: [UInt16] = []
        let saved = UserDefaults.standard.integer(forKey: "ztLastPort")
        if saved > 0 { candidates.append(UInt16(saved)) }
        candidates.append(contentsOf: [24180, 24181, 24182, 0])
        for p in candidates where port == 0 {
            _ = tryStart(port: p)
        }
    }

    private func tryStart(port p: UInt16) -> Bool {
        let params = NWParameters.tcp
        params.allowLocalEndpointReuse = true
        guard let loopback = IPv4Address("127.0.0.1"),
              let epPort = NWEndpoint.Port(rawValue: p) else { return false }
        params.requiredLocalEndpoint = NWEndpoint.hostPort(host: .ipv4(loopback), port: epPort)
        guard let l = try? NWListener(using: params) else { return false }
        let sema = DispatchSemaphore(value: 0)
        var bound = false
        l.stateUpdateHandler = { [weak self] state in
            if state == .ready {
                bound = true
                self?.port = epPort.rawValue
                UserDefaults.standard.set(Int(epPort.rawValue), forKey: "ztLastPort")
            }
            sema.signal()
        }
        l.newConnectionHandler = { [weak self] conn in
            self?.accept(conn)
        }
        l.start(queue: queue)
        _ = sema.wait(timeout: .now() + 1.5)
        if bound {
            listener = l
            return true
        }
        l.cancel()
        return false
    }

    // MARK: - 连接处理（手写 HTTP/1.1，支持 keep-alive）

    private final class ConnState {
        var buffer = Data()
    }

    private func accept(_ conn: NWConnection) {
        let st = ConnState()
        conn.start(queue: queue)
        pump(conn, st)
    }

    private func pump(_ conn: NWConnection, _ st: ConnState) {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 262144) { [weak self] data, _, isComplete, error in
            guard let self = self else { conn.cancel(); return }
            if let d = data { st.buffer.append(d) }
            if error != nil { conn.cancel(); return }
            while let req = HTTPRequest.parse(&st.buffer) {
                self.respond(conn, req)   // 恒 keep-alive：处理完继续留在循环里
            }
            if isComplete && st.buffer.isEmpty { conn.cancel(); return }
            self.pump(conn, st)
        }
    }

    private func respond(_ conn: NWConnection, _ req: HTTPRequest) {
        var status = "200 OK"
        var contentType = "text/html; charset=utf-8"
        var body = Data()

        if req.method == "GET" && (req.path == "/" || req.path == "/index.html") {
            body = tryLoad(webRoot.appendingPathComponent("index.html"))
            if body.isEmpty {
                status = "404 Not Found"
                body = Data("index.html missing in app bundle".utf8)
                contentType = "text/plain"
            }
        } else if req.method == "GET" && req.path.hasPrefix("/vendor/") {
            let rel = sanitizeRel(String(req.path.dropFirst("/vendor/".count)))
            let url = webRoot.appendingPathComponent("vendor", isDirectory: true).appendingPathComponent(rel)
            body = tryLoad(url)
            if body.isEmpty { status = "404 Not Found" } else { contentType = Self.mime(for: url) }
        } else if req.method == "GET" && req.path == "/__zt/inbox" {
            if let item = inboxProvider?() {
                body = item.0
                contentType = item.1
            } else {
                status = "404 Not Found"
                body = Data("no pending inbox".utf8)
                contentType = "text/plain"
            }
        } else if req.method == "POST" && req.path == "/__zt/export" {
            let name = Self.sanitizeFilename(req.query["name"] ?? "export.pdf")
            if exportSaver?(req.body, name) == true {
                contentType = "text/plain"
                body = Data("ok".utf8)
            } else {
                status = "500 Internal Server Error"
                contentType = "text/plain"
                body = Data("save failed".utf8)
            }
        } else {
            status = "404 Not Found"
            contentType = "text/plain"
            body = Data("not found".utf8)
        }

        let head = "HTTP/1.1 \(status)\r\nContent-Type: \(contentType)\r\n"
            + "Content-Length: \(body.count)\r\nCache-Control: no-store\r\nConnection: keep-alive\r\n\r\n"
        var resp = Data(head.utf8)
        resp.append(body)
        conn.send(content: resp, completion: .contentProcessed { _ in })
    }

    private func tryLoad(_ url: URL) -> Data {
        guard url.path.hasPrefix(webRoot.path) else { return Data() }   // 防目录穿越
        return (try? Data(contentsOf: url)) ?? Data()
    }

    private func sanitizeRel(_ s: String) -> String {
        let cleaned = s.replacingOccurrences(of: "..", with: "")
        let parts = cleaned.split(separator: "/").map { String($0) }.filter { !$0.isEmpty }
        return parts.joined(separator: "/")
    }

    static func sanitizeFilename(_ s: String) -> String {
        var t = s.replacingOccurrences(of: "/", with: "_")
        t = t.replacingOccurrences(of: "\\", with: "_")
        t = t.replacingOccurrences(of: "..", with: "_")
        t = t.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.isEmpty { t = "export.pdf" }
        return t
    }

    static func mime(for url: URL) -> String {
        switch url.pathExtension.lowercased() {
        case "html", "htm": return "text/html; charset=utf-8"
        case "js", "mjs": return "application/javascript"
        case "css": return "text/css; charset=utf-8"
        case "json", "map": return "application/json"
        case "pdf": return "application/pdf"
        case "png": return "image/png"
        case "jpg", "jpeg": return "image/jpeg"
        case "svg": return "image/svg+xml"
        case "txt": return "text/plain; charset=utf-8"
        default: return "application/octet-stream"
        }
    }
}

/// 极简 HTTP 请求解析：只支持 Content-Length 定长的普通请求（fetch/XHR 均满足）。
struct HTTPRequest {
    var method = ""
    var path = ""
    var query: [String: String] = [:]
    var body = Data()

    static func parse(_ buf: inout Data) -> HTTPRequest? {
        guard let headerRange = buf.range(of: Data("\r\n\r\n".utf8)) else { return nil }
        let headData = buf.subdata(in: buf.startIndex..<headerRange.lowerBound)
        guard let head = String(data: headData, encoding: .utf8) else { return nil }
        let lines = head.components(separatedBy: "\r\n")
        guard let first = lines.first else { return nil }
        let parts = first.components(separatedBy: " ")
        guard parts.count >= 2 else { return nil }

        var req = HTTPRequest()
        req.method = parts[0].uppercased()
        let target = parts[1]
        var pathPart = target
        if let qi = target.firstIndex(of: "?") {
            pathPart = String(target[..<qi])
            let qs = target[target.index(after: qi)...]
            for pair in qs.split(separator: "&") {
                let kv = pair.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
                let k = urlDecode(String(kv[0]))
                let v = kv.count > 1 ? urlDecode(String(kv[1])) : ""
                req.query[k] = v
            }
        }
        req.path = urlDecode(pathPart)

        var contentLength = 0
        for line in lines.dropFirst() {
            let lowered = line.lowercased()
            if lowered.hasPrefix("content-length:") {
                let v = line.dropFirst("content-length:".count).trimmingCharacters(in: .whitespaces)
                contentLength = Int(v) ?? 0
            }
        }
        let bodyStart = headerRange.upperBound
        let available = buf.distance(from: bodyStart, to: buf.endIndex)
        if available < contentLength { return nil }
        if contentLength > 0 {
            req.body = buf.subdata(in: bodyStart..<buf.index(bodyStart, offsetBy: contentLength))
        }
        let consumed = buf.distance(from: buf.startIndex, to: headerRange.upperBound) + contentLength
        buf.removeFirst(consumed)
        return req
    }

    static func urlDecode(_ s: String) -> String {
        let t = s.replacingOccurrences(of: "+", with: " ")
        return t.removingPercentEncoding ?? t
    }
}
