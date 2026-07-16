import AVFoundation

/// Native text-to-speech backing the web app's 🔊 buttons.
/// Replaces WKWebView's Web Speech API, which silently fails on devices
/// where the matching voice isn't installed or the audio session is muted.
final class SpeechManager {

    private let synthesizer = AVSpeechSynthesizer()

    init() {
        // .playback so study audio is heard even with the silent switch on.
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio)
    }

    func speak(text: String, languageCode: String) {
        stop()
        try? AVAudioSession.sharedInstance().setActive(true)

        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = bestVoice(for: languageCode)
        // Slightly slower than the default — matches the web app's 0.85 rate
        // and suits the app's senior audience.
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 0.9
        synthesizer.speak(utterance)
    }

    func stop() {
        synthesizer.stopSpeaking(at: .immediate)
    }

    /// Exact language match ("hi-IN"), then language-prefix match ("hi"),
    /// then nil (system default voice).
    private func bestVoice(for code: String) -> AVSpeechSynthesisVoice? {
        if let exact = AVSpeechSynthesisVoice(language: code) { return exact }
        let prefix = code.split(separator: "-").first.map(String.init) ?? code
        return AVSpeechSynthesisVoice.speechVoices()
            .first { $0.language.hasPrefix(prefix) }
    }
}
