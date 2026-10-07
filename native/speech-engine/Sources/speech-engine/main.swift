// speech-engine: Sirina's on-device speech helper.
//
//   speech-engine --probe                  print capabilities as one JSON line, exit 0
//   speech-engine serve                    JSON-lines requests on stdin, one response per line
//   speech-engine captions [--sample-rate 48000] [--language en] [--prompt "a, b"]
//                                          raw s16le mono PCM on stdin → caption lines on stdout
//
// serve requests (`id` is echoed back; one request is handled at a time):
//   {"id":1,"cmd":"load_whisper","model_dir":"…"}
//   {"id":2,"cmd":"transcribe","path":"mic.wav","start_s":0,"end_s":180,"language":"en","prompt":"…"}
//   {"id":3,"cmd":"draft","path":"mic.wav","start_s":0,"end_s":null,"language":"en","prompt":"…"}
//   {"id":4,"cmd":"load_diarizer","model_dir":"…"}
//   {"id":5,"cmd":"diarize","path":"system.wav","end_s":null}
//   {"id":6,"cmd":"status"}
//   {"id":7,"cmd":"install_speech_asset","language":"en"}
// Responses: {"id":…,"ok":true,…} or {"id":…,"ok":false,"error":"…"}. A malformed line
// never ends the loop.
import Foundation

Output.claimStdout()

let args = CommandLine.arguments
func option(_ name: String) -> String? {
    guard let i = args.firstIndex(of: name), i + 1 < args.count else { return nil }
    return args[i + 1]
}

func capabilities() async -> [String: Any] {
    var caps: [String: Any] = [
        "whisperkit": true,
        "speakerkit": true,
        "apple_speech": AppleSpeech.supported,
        "macos": ProcessInfo.processInfo.operatingSystemVersionString,
    ]
    if #available(macOS 26, *), AppleSpeech.supported {
        caps["apple_speech_asset_installed"] = await AppleSpeech.assetInstalled(language: option("--language"))
    }
    return caps
}

func powerStatus() -> [String: Any] {
    ["low_power": ProcessInfo.processInfo.isLowPowerModeEnabled]
}

let transcriber = Transcriber()
let splitter = SpeakerSplitter()

func handle(_ req: [String: Any]) async throws -> [String: Any] {
    let cmd = req["cmd"] as? String ?? ""
    func str(_ k: String) -> String? { req[k] as? String }
    func num(_ k: String) -> Double? { (req[k] as? NSNumber)?.doubleValue }
    func path() throws -> String {
        guard let p = str("path") else { throw HelperError.badRequest("missing path") }
        return p
    }

    switch cmd {
    case "load_whisper":
        guard let dir = str("model_dir") else { throw HelperError.badRequest("missing model_dir") }
        try await transcriber.load(modelFolder: dir)
        return [:]
    case "transcribe":
        return try await transcriber.transcribe(
            path: try path(), startS: num("start_s") ?? 0, endS: num("end_s"),
            language: str("language"), prompt: str("prompt"))
    case "draft":
        guard #available(macOS 26, *), AppleSpeech.supported else {
            throw HelperError.unsupported("on-device draft needs macOS 26")
        }
        let segments = try await AppleSpeech.draft(
            path: try path(), startS: num("start_s") ?? 0, endS: num("end_s"),
            language: str("language"), prompt: str("prompt"))
        return ["segments": segments]
    case "install_speech_asset":
        guard #available(macOS 26, *), AppleSpeech.supported else {
            throw HelperError.unsupported("on-device speech needs macOS 26")
        }
        try await AppleSpeech.ensureAsset(AppleSpeech.makeTranscriber(live: false, language: str("language")))
        return [:]
    case "load_diarizer":
        guard let dir = str("model_dir") else { throw HelperError.badRequest("missing model_dir") }
        try await splitter.load(modelFolder: dir)
        return [:]
    case "diarize":
        return try await splitter.diarize(path: try path(), endS: num("end_s"))
    case "status":
        return powerStatus().merging(await capabilities()) { a, _ in a }
    default:
        throw HelperError.badRequest("unknown cmd \(cmd)")
    }
}

func serve() async {
    while let line = readLine(strippingNewline: true) {
        if line.trimmingCharacters(in: .whitespaces).isEmpty { continue }
        guard let data = line.data(using: .utf8),
              let req = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
            Output.send(["id": NSNull(), "ok": false, "error": "malformed request"])
            continue
        }
        let id = req["id"] ?? NSNull()
        do {
            var resp = try await handle(req)
            resp["id"] = id
            resp["ok"] = true
            Output.send(resp)
        } catch {
            Output.send(["id": id, "ok": false, "error": "\(error)"])
        }
    }
}

switch args.dropFirst().first {
case "--probe":
    Output.send(await capabilities())
case "serve":
    await serve()
case "captions":
    guard #available(macOS 26, *), AppleSpeech.supported else {
        Output.log("captions need macOS 26 with on-device speech recognition")
        exit(3)
    }
    do {
        try await AppleSpeech.captions(
            sampleRate: Double(option("--sample-rate") ?? "48000") ?? 48000,
            language: option("--language"), prompt: option("--prompt"))
    } catch {
        Output.log("captions failed: \(error)")
        exit(2)
    }
default:
    Output.log("usage: speech-engine --probe | serve | captions [--sample-rate N] [--language xx] [--prompt \"a, b\"]")
    exit(64)
}
