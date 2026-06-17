## ADDED Requirements

### Requirement: Copy transcript to clipboard

The recording detail view SHALL provide "Copy as Markdown" and "Copy as Text" actions that write the recording's exported content to the system clipboard, replacing file-download export.

#### Scenario: Copy as Markdown

- **WHEN** the user clicks "Copy as Markdown"
- **THEN** the recording's markdown export (transcript and summary) is written to the clipboard
- **AND** a transient confirmation is shown

#### Scenario: Copy as Text

- **WHEN** the user clicks "Copy as Text"
- **THEN** the recording's plain-text export is written to the clipboard
- **AND** a transient confirmation is shown

#### Scenario: Clipboard API unavailable

- **WHEN** the async clipboard API is not available in the runtime
- **THEN** the system falls back to a copy mechanism that still places the content on the clipboard
