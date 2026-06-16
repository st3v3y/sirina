# recording-store Specification

## Purpose
TBD - created by archiving change record-to-file. Update Purpose after archive.
## Requirements
### Requirement: Recording entity with lifecycle status

The system SHALL persist each recording as a `Recording` with at least: identifier, optional title, created/started/ended timestamps, duration, status, detected/forced language, and references to its audio files. Status MUST be one of `recording`, `processing`, `ready`, `failed`.

#### Scenario: Recording is created on start

- **WHEN** a recording starts
- **THEN** a `Recording` row is created with status `recording` and a start timestamp

#### Scenario: Status transitions are persisted

- **WHEN** a recording is stopped
- **THEN** its status becomes `processing` and its ended timestamp and duration are stored

### Requirement: On-disk audio layout

Audio files for a recording SHALL be stored under a per-recording directory and referenced from the `Recording` row. The directory MUST be excluded from version control.

#### Scenario: Files are referenced and gitignored

- **WHEN** a recording has been captured
- **THEN** its `Recording` row references the mic/system/mixed file paths under a per-recording directory
- **AND** that directory is covered by `.gitignore`

### Requirement: Clean v2 schema with no v1 migration

The v2 schema SHALL be created fresh. The system MUST NOT attempt to migrate or read prior `Meeting`-era data.

#### Scenario: Fresh database initializes cleanly

- **WHEN** the backend initializes its database with no existing v2 tables
- **THEN** the v2 schema is created and seeded without referencing any `Meeting` table

### Requirement: Transcript and summary records reference a recording

`Segment`, `Summary`, and `QAMessage` records SHALL reference a `Recording` by id (populated by later capabilities).

#### Scenario: Foreign keys point to recording

- **WHEN** the schema is created
- **THEN** `Segment`, `Summary`, and `QAMessage` each carry a `recording_id` foreign key

