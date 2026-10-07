// swift-tools-version: 5.10
// Speech helper for Sirina: final transcription (WhisperKit), speaker splitting (SpeakerKit),
// and on-device draft/captions (Apple SpeechTranscriber, macOS 26+). See README.md.
import PackageDescription

let package = Package(
    name: "speech-engine",
    platforms: [.macOS(.v14)],
    dependencies: [
        // Pinned on purpose: an upgrade is a deliberate bump plus a rerun of the
        // transcription validation (openspec change faster-transcription-live-captions).
        .package(url: "https://github.com/argmaxinc/argmax-oss-swift.git", exact: "1.1.0"),
    ],
    targets: [
        .executableTarget(
            name: "speech-engine",
            dependencies: [
                .product(name: "WhisperKit", package: "argmax-oss-swift"),
                .product(name: "SpeakerKit", package: "argmax-oss-swift"),
            ]
        ),
    ]
)
