import Foundation
@preconcurrency import WhisperKit

/// Final-pass transcription with WhisperKit. One model stays loaded for the process lifetime.
actor Transcriber {
    private var whisperKit: WhisperKit?
    private var loadedFolder: String?

    func load(modelFolder: String) async throws {
        if loadedFolder == modelFolder, whisperKit != nil { return }
        let config = WhisperKitConfig(
            modelFolder: modelFolder,
            verbose: false,
            logLevel: .error,
            prewarm: false,
            load: true,
            download: false
        )
        whisperKit = try await WhisperKit(config)
        loadedFolder = modelFolder
    }

    /// Transcribe `[startS, endS)` of a WAV file. Times in the result are absolute
    /// (recording time), so the backend never has to offset them.
    func transcribe(path: String, startS: Double, endS: Double?, language: String?, prompt: String?) async throws -> [String: Any] {
        guard let whisperKit else { throw HelperError.notLoaded("whisper model not loaded") }
        let buffer = try AudioProcessor.loadAudio(fromPath: path, startTime: startS, endTime: endS)
        let samples = AudioProcessor.convertBufferToArray(buffer: buffer)
        if samples.isEmpty {
            return ["segments": [], "language": language ?? NSNull()]
        }

        var options = DecodingOptions(
            task: .transcribe,
            language: language,
            temperature: 0,
            usePrefillPrompt: language != nil,
            detectLanguage: language == nil,
            skipSpecialTokens: true,
            wordTimestamps: true,
            compressionRatioThreshold: 2.4,
            logProbThreshold: -1.0,
            noSpeechThreshold: 0.6,
            chunkingStrategy: .vad
        )
        if let prompt, !prompt.trimmingCharacters(in: .whitespaces).isEmpty, let tokenizer = whisperKit.tokenizer {
            options.promptTokens = tokenizer.encode(text: " " + prompt.trimmingCharacters(in: .whitespaces))
                .filter { $0 < tokenizer.specialTokens.specialTokenBegin }
            options.usePrefillPrompt = true
        }

        let results = try await whisperKit.transcribe(audioArray: samples, decodeOptions: options)
        // Times come back relative to the slice; make them absolute. WhisperKit can place the
        // cut-off last phrase of a single (<=30 s) window past the end of the audio, and VAD
        // chunks can arrive out of order, so clamp every time into the window and sort.
        let windowStart = startS
        let windowEnd = startS + Double(samples.count) / Double(WhisperKit.sampleRate)
        func abs(_ t: Float) -> Double { min(max(Double(t) + windowStart, windowStart), windowEnd) }
        var segments: [[String: Any]] = []
        var detected: String? = language
        for result in results {
            if detected == nil, !result.language.isEmpty { detected = result.language }
            for seg in result.segments {
                let text = Self.clean(seg.text)
                if text.isEmpty { continue }
                let words: [[Any]] = (seg.words ?? []).compactMap { w in
                    let word = w.word.trimmingCharacters(in: .whitespaces)
                    if word.isEmpty { return nil }
                    return [abs(w.start), abs(w.end), word]
                }
                segments.append(["start": abs(seg.start), "end": abs(seg.end), "text": text, "words": words])
            }
        }
        segments.sort { ($0["start"] as! Double) < ($1["start"] as! Double) }
        return ["segments": segments, "language": detected ?? NSNull(), "audio_s": Double(samples.count) / Double(WhisperKit.sampleRate)]
    }

    /// Strip Whisper control tokens such as `<|startoftranscript|>` that can survive in text.
    static func clean(_ text: String) -> String {
        text.replacingOccurrences(of: "<\\|[^|]*\\|>", with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

enum HelperError: Error, CustomStringConvertible {
    case notLoaded(String)
    case badRequest(String)
    case unsupported(String)

    var description: String {
        switch self {
        case .notLoaded(let m), .badRequest(let m), .unsupported(let m): return m
        }
    }
}
