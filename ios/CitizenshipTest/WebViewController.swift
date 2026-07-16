import UIKit
import WebKit

/// Full-screen WKWebView hosting the study app. The entire web app
/// (index.html, style.css, questions.js, translations/) ships inside the
/// app bundle, so everything except the live .gov data works offline.
class WebViewController: UIViewController, WKScriptMessageHandler {

    private var webView: WKWebView!
    private let speech = SpeechManager()

    override func loadView() {
        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true
        // Let JS start speech/audio without an extra user gesture.
        config.mediaTypesRequiringUserActionForPlayback = []

        // JS calls window.webkit.messageHandlers.speech.postMessage({...})
        // instead of the unreliable Web Speech API when running in the app.
        config.userContentController.add(self, name: "speech")

        // WebKit blocks fetch() on file:// URLs, so the web side can't read
        // the bundled gov_data.json itself. Inject it as a global instead;
        // loadGovData() falls back to it when every network source fails.
        // The file is scraper output copied fresh into the bundle each build.
        if let dataURL = Bundle.main.url(forResource: "gov_data", withExtension: "json"),
           let json = try? String(contentsOf: dataURL, encoding: .utf8) {
            let script = WKUserScript(
                source: "window.GOV_DATA_BUNDLED = \(json);",
                injectionTime: .atDocumentStart,
                forMainFrameOnly: true
            )
            config.userContentController.addUserScript(script)
        }

        webView = WKWebView(frame: .zero, configuration: config)
        #if DEBUG
        // Required since iOS 16.4 for Safari Web Inspector to see this view.
        if #available(iOS 16.4, *) {
            webView.isInspectable = true
        }
        #endif
        webView.isOpaque = false
        webView.backgroundColor = UIColor(red: 0.96, green: 0.96, blue: 0.94, alpha: 1) // matches --offwhite
        webView.scrollView.contentInsetAdjustmentBehavior = .automatic

        // Web content ships in the bundle; no pull-to-refresh surprises.
        webView.scrollView.bounces = true

        view = webView
    }

    override func viewDidLoad() {
        super.viewDidLoad()

        guard
            let indexURL = Bundle.main.url(forResource: "index", withExtension: "html"),
            let webRoot = Bundle.main.resourceURL
        else {
            assertionFailure("index.html missing from app bundle")
            return
        }
        // allowingReadAccessTo the bundle root so <script src="translations/…">
        // and other same-folder resources load from file://
        webView.loadFileURL(indexURL, allowingReadAccessTo: webRoot)
    }

    override var preferredStatusBarStyle: UIStatusBarStyle {
        // Header bar is dark blue — use light status bar text over it.
        .lightContent
    }

    // MARK: - WKScriptMessageHandler

    func userContentController(
        _ userContentController: WKUserContentController,
        didReceive message: WKScriptMessage
    ) {
        guard message.name == "speech", let body = message.body as? [String: Any],
              let action = body["action"] as? String
        else { return }

        switch action {
        case "speak":
            if let text = body["text"] as? String, !text.isEmpty {
                speech.speak(text: text, languageCode: body["lang"] as? String ?? "en-US")
            }
        case "stop":
            speech.stop()
        default:
            break
        }
    }
}
