import UIKit
import UniformTypeIdentifiers

/// Share-sheet target: share a Coop receipt PDF straight into the home app.
final class ShareViewController: UIViewController {
    private let label = UILabel()
    private let serverBases = [
        "http://100.92.219.95:8000",   // Tailscale
        "http://192.168.8.147:8000"    // Home LAN
    ]

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        label.numberOfLines = 0
        label.textAlignment = .center
        label.font = .preferredFont(forTextStyle: .body)
        label.text = "Importing receipt…"
        label.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(label)
        NSLayoutConstraint.activate([
            label.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            label.centerYAnchor.constraint(equalTo: view.centerYAnchor),
            label.leadingAnchor.constraint(greaterThanOrEqualTo: view.leadingAnchor, constant: 24),
            label.trailingAnchor.constraint(lessThanOrEqualTo: view.trailingAnchor, constant: -24),
        ])
        importReceipt()
    }

    private func importReceipt() {
        guard let input = extensionContext?.inputItems.first as? NSExtensionItem,
              let attachments = input.attachments, let provider = attachments.first else {
            finish("Nothing to import.")
            return
        }

        // 1) Direct PDF/file attachment.
        let pdf = UTType.pdf.identifier
        if provider.hasItemConformingToTypeIdentifier(pdf) {
            provider.loadDataRepresentation(forTypeIdentifier: pdf) { [weak self] data, error in
                DispatchQueue.main.async {
                    if let data, !data.isEmpty { self?.upload(data) }
                    else { self?.finish("Couldn't read the file: \(error?.localizedDescription ?? "unknown error")") }
                }
            }
            return
        }

        // 2) A URL (Coop sometimes shares a link).
        if provider.hasItemConformingToTypeIdentifier(UTType.url.identifier) {
            provider.loadItem(forTypeIdentifier: UTType.url.identifier, options: nil) { [weak self] item, _ in
                DispatchQueue.main.async {
                    guard let self, let url = item as? URL else { self?.finish("Couldn't read the link."); return }
                    if url.pathExtension.lowercased() == "pdf" { self.download(url) }
                    else { self.finish("Share the PDF file directly.") }
                }
            }
            return
        }

        // 3) Any generic data fallback.
        if let first = provider.registeredTypeIdentifiers.first(where: { UTType($0)?.conforms(to: .data) ?? false }) {
            provider.loadDataRepresentation(forTypeIdentifier: first) { [weak self] data, error in
                DispatchQueue.main.async {
                    if let data, !data.isEmpty { self?.upload(data) }
                    else { self?.finish("Couldn't read the file.") }
                }
            }
            return
        }

        finish("Please share the receipt PDF.")
    }

    private func download(_ url: URL) {
        label.text = "Downloading receipt…"
        URLSession.shared.dataTask(with: url) { [weak self] data, _, error in
            DispatchQueue.main.async {
                if let data, !data.isEmpty { self?.upload(data) }
                else { self?.finish("Download failed: \(error?.localizedDescription ?? "no data")") }
            }
        }.resume()
    }

    private func upload(_ data: Data) {
        label.text = "Importing receipt…"
        tryUpload(data, at: 0)
    }

    private func tryUpload(_ data: Data, at index: Int) {
        guard index < serverBases.count else { finish("Couldn't reach the server."); return }
        guard let url = URL(string: serverBases[index] + "/api/receipts/import") else { finish("Bad server URL."); return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        let boundary = "Home-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        var body = Data()
        func append(_ s: String) { body.append(Data(s.utf8)) }
        append("--\(boundary)\r\n")
        append("Content-Disposition: form-data; name=\"file\"; filename=\"receipt.pdf\"\r\n")
        append("Content-Type: application/pdf\r\n\r\n")
        body.append(data)
        append("\r\n--\(boundary)--\r\n")
        request.httpBody = body

        URLSession.shared.dataTask(with: request) { [weak self] respData, _, error in
            DispatchQueue.main.async {
                guard let self else { return }
                if let error {
                    // Transport failure → try the next server address.
                    self.tryUpload(data, at: index + 1)
                    return
                }
                var msg = "Receipt imported ✅"
                if let respData, let json = try? JSONSerialization.jsonObject(with: respData) as? [String: Any] {
                    if json["already_imported"] as? Bool == true { msg = "Already imported ✅" }
                    else if let items = json["items"] as? [[String: Any]] { msg = "Added \(items.count) items ✅" }
                    else if let detail = json["detail"] as? String { msg = "Error: \(detail)" }
                }
                self.finish(msg)
            }
        }.resume()
    }

    private func finish(_ message: String) {
        label.text = message
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) { [weak self] in
            self?.extensionContext?.completeRequest(returningItems: nil)
        }
    }
}
