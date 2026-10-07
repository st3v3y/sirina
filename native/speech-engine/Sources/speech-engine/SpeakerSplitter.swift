import Foundation
@preconcurrency import SpeakerKit
@preconcurrency import WhisperKit

/// Speaker splitting (diarization) with SpeakerKit. Returns turns plus one centroid
/// embedding per speaker for cross-recording voice matching.
actor SpeakerSplitter {
    private var speakerKit: SpeakerKit?
    private var loadedFolder: String?

    func load(modelFolder: String) async throws {
        if loadedFolder == modelFolder, speakerKit != nil { return }
        let config = PyannoteConfig(
            modelFolder: modelFolder,
            download: false,
            verbose: false
        )
        speakerKit = try await SpeakerKit(config)
        loadedFolder = modelFolder
    }

    func diarize(path: String, endS: Double?) async throws -> [String: Any] {
        guard let speakerKit else { throw HelperError.notLoaded("speaker model not loaded") }
        let buffer = try AudioProcessor.loadAudio(fromPath: path, startTime: 0, endTime: endS)
        let samples = AudioProcessor.convertBufferToArray(buffer: buffer)
        if samples.isEmpty { return ["turns": [], "embeddings": [:]] }

        let result = try await speakerKit.diarize(audioArray: samples, options: PyannoteDiarizationOptions())
        var turns: [[String: Any]] = []
        for seg in result.segments {
            guard let id = seg.speaker.speakerId else { continue }  // overlapped / no match
            turns.append(["start": Double(seg.startTime), "end": Double(seg.endTime), "speaker": "S\(id)"])
        }
        var embeddings: [String: [Double]] = [:]
        for (id, centroid) in result.speakerCentroidEmbeddings {
            embeddings["S\(id)"] = centroid.map(Double.init)
        }
        return ["turns": turns, "embeddings": embeddings]
    }
}
