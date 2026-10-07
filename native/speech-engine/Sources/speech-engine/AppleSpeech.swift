import AVFoundation
import Foundation
import Speech

/// On-device draft transcription and live captions with Apple's SpeechTranscriber
/// (macOS 26+). Lower quality than the final pass, but nearly free: it is used for the
/// draft transcript and for captions only.
enum AppleSpeech {
    static var supported: Bool {
        if #available(macOS 26, *) { return SpeechTranscriber.isAvailable }
        return false
    }

    @available(macOS 26, *)
    static func makeTranscriber(live: Bool, language: String?) -> SpeechTranscriber {
        SpeechTranscriber(
            locale: Locale(identifier: language.map(localeIdentifier) ?? "en-US"),
            transcriptionOptions: [],
            reportingOptions: live ? [.volatileResults, .fastResults] : [],
            attributeOptions: [.audioTimeRange]
        )
    }

    /// Whisper uses bare language codes ("en"); SpeechTranscriber wants a locale.
    static func localeIdentifier(_ code: String) -> String {
        let defaults = ["en": "en-US", "de": "de-DE", "fr": "fr-FR", "es": "es-ES", "it": "it-IT", "pt": "pt-BR", "nl": "nl-NL"]
        return code.contains("-") ? code : (defaults[code] ?? code)
    }

    /// Install the language asset if macOS doesn't have it yet (Apple-managed download).
    @available(macOS 26, *)
    static func ensureAsset(_ transcriber: SpeechTranscriber) async throws {
        if let request = try await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
            try await request.downloadAndInstall()
        }
    }

    @available(macOS 26, *)
    static func assetInstalled(language: String?) async -> Bool {
        let t = makeTranscriber(live: false, language: language)
        return await AssetInventory.status(forModules: [t]) == .installed
    }

    @available(macOS 26, *)
    private static func analyzer(for transcriber: SpeechTranscriber, hints: [String]) async throws -> SpeechAnalyzer {
        let analyzer = SpeechAnalyzer(modules: [transcriber])
        if !hints.isEmpty {
            let ctx = AnalysisContext()
            ctx.contextualStrings[.general] = hints
            try await analyzer.setContext(ctx)
        }
        return analyzer
    }

    static func hints(from prompt: String?) -> [String] {
        (prompt ?? "").split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }

    // MARK: Draft (offline, from a file slice)

    /// Settled segments for `[startS, endS)` of a WAV file, with absolute times.
    @available(macOS 26, *)
    static func draft(path: String, startS: Double, endS: Double?, language: String?, prompt: String?) async throws -> [[String: Any]] {
        let transcriber = makeTranscriber(live: false, language: language)
        try await ensureAsset(transcriber)
        let analyzer = try await analyzer(for: transcriber, hints: hints(from: prompt))

        let file = try AVAudioFile(forReading: URL(fileURLWithPath: path))
        let sr = file.processingFormat.sampleRate
        let startFrame = AVAudioFramePosition(startS * sr)
        let endFrame = min(endS.map { AVAudioFramePosition($0 * sr) } ?? file.length, file.length)
        guard endFrame > startFrame else { return [] }
        file.framePosition = startFrame

        guard let target = await SpeechAnalyzer.bestAvailableAudioFormat(compatibleWith: [transcriber]),
              let converter = AVAudioConverter(from: file.processingFormat, to: target) else {
            throw HelperError.unsupported("no compatible audio format for SpeechTranscriber")
        }

        let collector = Task { () -> [[String: Any]] in
            var out: [[String: Any]] = []
            for try await r in transcriber.results where r.isFinal {
                let text = String(r.text.characters).trimmingCharacters(in: .whitespacesAndNewlines)
                if text.isEmpty { continue }
                out.append(["start": r.range.start.seconds + startS, "end": r.range.end.seconds + startS, "text": text])
            }
            return out
        }

        let (stream, cont) = AsyncStream<AnalyzerInput>.makeStream()
        try await analyzer.start(inputSequence: stream)
        let chunk = AVAudioFrameCount(sr)  // 1 s per buffer
        var remaining = endFrame - startFrame
        while remaining > 0 {
            let n = AVAudioFrameCount(min(AVAudioFramePosition(chunk), remaining))
            guard let inBuf = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: n) else { break }
            try file.read(into: inBuf, frameCount: n)
            if inBuf.frameLength == 0 { break }
            remaining -= AVAudioFramePosition(inBuf.frameLength)
            if let outBuf = convert(inBuf, with: converter, to: target) { cont.yield(AnalyzerInput(buffer: outBuf)) }
        }
        cont.finish()
        try await analyzer.finalizeAndFinishThroughEndOfInput()
        return try await collector.value
    }

    // MARK: Captions (live, raw PCM on stdin)

    /// Read 48 kHz mono s16le PCM from stdin until EOF and emit caption lines:
    /// `{"kind":"provisional"|"settled","start":s,"end":s,"text":...}`. Times count from the
    /// first sample received, which the recorder aligns with the track's WAV.
    @available(macOS 26, *)
    static func captions(sampleRate: Double, language: String?, prompt: String?) async throws {
        let transcriber = makeTranscriber(live: true, language: language)
        try await ensureAsset(transcriber)
        let analyzer = try await analyzer(for: transcriber, hints: hints(from: prompt))
        guard let inFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: sampleRate, channels: 1, interleaved: true),
              let target = await SpeechAnalyzer.bestAvailableAudioFormat(compatibleWith: [transcriber]),
              let converter = AVAudioConverter(from: inFormat, to: target) else {
            throw HelperError.unsupported("no compatible audio format for SpeechTranscriber")
        }

        let printer = Task {
            for try await r in transcriber.results {
                let text = String(r.text.characters).trimmingCharacters(in: .whitespacesAndNewlines)
                if text.isEmpty { continue }
                Output.send([
                    "kind": r.isFinal ? "settled" : "provisional",
                    "start": r.range.start.seconds,
                    "end": r.range.end.seconds,
                    "text": text,
                ])
            }
        }

        let (stream, cont) = AsyncStream<AnalyzerInput>.makeStream()
        try await analyzer.start(inputSequence: stream)
        let bytesPerChunk = Int(sampleRate / 10) * 2  // 100 ms of s16 mono
        let stdin = FileHandle.standardInput
        var pending = Data()
        while true {
            let data = stdin.readData(ofLength: bytesPerChunk)
            if data.isEmpty { break }  // EOF: the recording stopped
            pending.append(data)
            let usable = pending.count - pending.count % 2
            if usable == 0 { continue }
            let frames = AVAudioFrameCount(usable / 2)
            guard let inBuf = AVAudioPCMBuffer(pcmFormat: inFormat, frameCapacity: frames) else { continue }
            inBuf.frameLength = frames
            pending.prefix(usable).withUnsafeBytes { raw in
                if let dst = inBuf.int16ChannelData?[0], let src = raw.baseAddress {
                    memcpy(dst, src, usable)
                }
            }
            pending.removeFirst(usable)
            if let outBuf = convert(inBuf, with: converter, to: target) { cont.yield(AnalyzerInput(buffer: outBuf)) }
        }
        cont.finish()
        try await analyzer.finalizeAndFinishThroughEndOfInput()
        _ = try await printer.value
    }

    private static func convert(_ input: AVAudioPCMBuffer, with converter: AVAudioConverter, to target: AVAudioFormat) -> AVAudioPCMBuffer? {
        let ratio = target.sampleRate / input.format.sampleRate
        let capacity = AVAudioFrameCount(Double(input.frameLength) * ratio) + 64
        guard let out = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: capacity) else { return nil }
        var given = false
        var error: NSError?
        converter.convert(to: out, error: &error) { _, status in
            if given { status.pointee = .noDataNow; return nil }
            given = true
            status.pointee = .haveData
            return input
        }
        if let error { Output.log("audio conversion failed: \(error.localizedDescription)"); return nil }
        return out.frameLength > 0 ? out : nil
    }
}
