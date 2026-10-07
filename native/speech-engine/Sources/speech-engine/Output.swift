import Foundation

/// The JSON-lines channel to the backend.
///
/// Libraries we link may print to stdout, which would corrupt the protocol. At startup we
/// keep a private duplicate of the real stdout for our messages and point fd 1 at stderr,
/// so any stray library output lands in the backend's log instead of the protocol stream.
enum Output {
    nonisolated(unsafe) private static var handle = FileHandle.standardOutput
    private static let lock = NSLock()

    static func claimStdout() {
        let protocolFd = dup(STDOUT_FILENO)
        if protocolFd >= 0 {
            handle = FileHandle(fileDescriptor: protocolFd, closeOnDealloc: false)
            dup2(STDERR_FILENO, STDOUT_FILENO)
        }
    }

    /// Write one JSON object as a single line.
    static func send(_ object: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: object, options: []) else {
            log("could not encode response")
            return
        }
        lock.lock()
        defer { lock.unlock() }
        handle.write(data)
        handle.write(Data([0x0A]))
    }

    static func log(_ message: String) {
        FileHandle.standardError.write(Data("speech-engine: \(message)\n".utf8))
    }
}
