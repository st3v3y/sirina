// system-audio-capture — captures the macOS system audio output mix via
// ScreenCaptureKit and writes raw PCM to stdout for the Python backend.
//
// Contract (matches the recorder's WAV writer):  48 kHz · mono · s16le · little-endian.
//
// Usage:
//   system-audio-capture            capture system audio → stdout until terminated (SIGTERM)
//   system-audio-capture --probe    verify it can run + has Screen Recording permission;
//                                    exit 0 if ok, non-zero otherwise (used for availability)
//
// Requires macOS 13+ and the Screen Recording permission (granted to the host app).
import AVFoundation
import CoreMedia
import Foundation
import ScreenCaptureKit

let SAMPLE_RATE = 48_000
let CHANNELS = 1

/// Receives audio sample buffers and writes interleaved s16le to stdout.
final class AudioOutput: NSObject, SCStreamOutput {
    private let out = FileHandle.standardOutput

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, sampleBuffer.isValid, CMSampleBufferDataIsReady(sampleBuffer) else { return }
        do {
            try sampleBuffer.withAudioBufferList { abl, _ in
                guard let buffer = abl.first, let mData = buffer.mData else { return }
                let channels = max(1, Int(buffer.mNumberChannels))
                let total = Int(buffer.mDataByteSize) / MemoryLayout<Float32>.size
                let floats = mData.bindMemory(to: Float32.self, capacity: total)
                let frames = total / channels
                var pcm = [Int16](repeating: 0, count: frames)
                for f in 0..<frames {
                    // Downmix to mono if the buffer arrived interleaved stereo.
                    var sum: Float = 0
                    for c in 0..<channels { sum += floats[f * channels + c] }
                    let s = max(-1.0, min(1.0, sum / Float(channels)))
                    pcm[f] = Int16((s * 32767.0).rounded())
                }
                pcm.withUnsafeBytes { out.write(Data($0)) }
            }
        } catch {
            FileHandle.standardError.write(Data("audio buffer error: \(error)\n".utf8))
        }
    }
}

func shareableContent() async throws -> SCShareableContent {
    // Getting shareable content triggers / requires the Screen Recording permission.
    try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
}

func makeConfig() -> SCStreamConfiguration {
    let config = SCStreamConfiguration()
    config.capturesAudio = true
    config.excludesCurrentProcessAudio = true  // never capture our own playback (no feedback)
    config.sampleRate = SAMPLE_RATE
    config.channelCount = CHANNELS
    // SCStream always captures video too; keep it tiny and ignore it.
    config.width = 2
    config.height = 2
    config.minimumFrameInterval = CMTime(value: 1, timescale: 1)
    return config
}

func runProbe() async {
    do {
        _ = try await shareableContent()
        FileHandle.standardError.write(Data("probe ok\n".utf8))
        exit(0)
    } catch {
        FileHandle.standardError.write(Data("screen recording unavailable: \(error)\n".utf8))
        exit(3)
    }
}

func runCapture() async {
    do {
        let content = try await shareableContent()
        guard let display = content.displays.first else {
            FileHandle.standardError.write(Data("no display available for capture\n".utf8))
            exit(4)
        }
        let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])
        let stream = SCStream(filter: filter, configuration: makeConfig(), delegate: nil)
        // SCStream holds stream outputs WEAKLY — keep a strong ref for the whole capture,
        // otherwise the audio callback never fires and we record silence.
        let output = AudioOutput()
        try stream.addStreamOutput(output, type: .audio, sampleHandlerQueue: DispatchQueue(label: "audio"))
        try await stream.startCapture()
        FileHandle.standardError.write(Data("capturing system audio (48kHz mono s16le)\n".utf8))
        // Run until the parent terminates us (SIGTERM). `output`/`stream` stay retained.
        try await Task.sleep(nanoseconds: UInt64.max)
        withExtendedLifetime((stream, output)) {}
    } catch {
        FileHandle.standardError.write(Data("capture failed: \(error)\n".utf8))
        exit(2)
    }
}

if CommandLine.arguments.contains("--probe") {
    await runProbe()
} else {
    await runCapture()
}
