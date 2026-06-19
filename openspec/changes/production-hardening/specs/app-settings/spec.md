## ADDED Requirements

### Requirement: Secret settings are stored in the OS keyring

Secret settings SHALL be stored in the operating system's credential store (macOS Keychain, Windows Credential Manager, or Linux Secret Service) through the existing secret seam, falling back to the database only when no OS keyring backend is available. When a keyring is available, secrets MUST NOT be stored as plaintext in the database, and any existing plaintext secret SHALL be migrated into the keyring.

#### Scenario: A secret is stored in the keyring

- **WHEN** the user saves a secret setting and an OS keyring is available
- **THEN** the secret is written to the OS keyring and is not stored as plaintext in the database

#### Scenario: Fallback without a keyring

- **WHEN** no OS keyring backend is available
- **THEN** the secret is stored via the database fallback and the app continues to work

#### Scenario: Existing plaintext secret is migrated

- **WHEN** the app starts with a keyring available and a plaintext secret present in the database
- **THEN** the secret is moved into the keyring and removed from the database

#### Scenario: Reads are unchanged for callers

- **WHEN** code reads a secret via the secret seam
- **THEN** it receives the effective value regardless of whether it is stored in the keyring or the database fallback
