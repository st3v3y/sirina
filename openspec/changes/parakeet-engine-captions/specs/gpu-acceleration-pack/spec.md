## ADDED Requirements

### Requirement: GPU acceleration is an optional download

On Windows and Linux, the model manager SHALL offer an "NVIDIA GPU acceleration" pack for the faster-whisper engine. The pack contains the CUDA runtime libraries faster-whisper needs (cuBLAS and cuDNN) and shows its approximate size. The pack MUST NOT be bundled with the app, MUST be downloaded only when the user installs it, and MUST be stored in the app's data directory. Every downloaded archive MUST match a checksum pinned in the app before anything from it is extracted. The pack MUST count as installed only once all files are extracted. The pack MUST NOT be offered on macOS.

#### Scenario: Install the pack

- **WHEN** a Windows user with an NVIDIA GPU installs the GPU acceleration pack
- **THEN** the libraries are downloaded into the data directory with progress shown
- **AND** the pack is listed as installed with its size on disk

#### Scenario: Tampered or truncated download

- **WHEN** a downloaded library archive does not match the checksum pinned in the app
- **THEN** nothing from it is installed or loaded, and the pack shows a download error with a retry

#### Scenario: Not offered on macOS

- **WHEN** the model manager is opened on macOS
- **THEN** no GPU acceleration pack is listed

### Requirement: faster-whisper uses the GPU when the pack and a GPU are present

When the GPU pack is installed and an NVIDIA GPU is usable, the faster-whisper engine SHALL load on CUDA with a GPU-appropriate compute type (float16 by default). When the pack is missing, the GPU is not detected, or loading on CUDA fails, the engine MUST load on the CPU instead, and the reason MUST be recorded so Settings can show it. The active device MUST be shown in Settings.

#### Scenario: GPU in use

- **WHEN** faster-whisper is the active engine, the pack is installed, and an NVIDIA GPU is detected
- **THEN** transcription runs on CUDA and Settings shows "GPU (CUDA)" as the device

#### Scenario: Driver too old

- **WHEN** the pack is installed but loading on CUDA fails (e.g. an outdated NVIDIA driver)
- **THEN** the engine loads on the CPU
- **AND** Settings shows that the GPU could not be used, with the error summary

### Requirement: The GPU pack can be removed

Users SHALL be able to delete the installed GPU pack from the model manager. Deleting it while faster-whisper runs on CUDA MUST be refused while a job is running. Otherwise it takes effect at the next engine reload, and the engine uses the CPU after that.

#### Scenario: Remove the pack

- **WHEN** the user deletes the GPU pack while no job is running
- **THEN** its files are removed and the next engine load uses the CPU
