## ADDED Requirements

### Requirement: People directory aggregates across recordings

The system SHALL provide a People directory listing every `Person`, with the number of recordings they appear in and the date of their most recent recording.

#### Scenario: Directory shows counts and last-seen

- **WHEN** the user opens the People directory
- **THEN** each Person is shown with a recording count and their most recent recording date

### Requirement: Renaming a Person is global

Renaming a `Person` in the directory SHALL update that Person everywhere they are linked.

#### Scenario: Global rename

- **WHEN** the user renames a Person in the directory
- **THEN** every recording where a speaker is linked to that Person reflects the new name

### Requirement: Deleting a Person unlinks speakers

Deleting a `Person` SHALL unlink any speakers referencing them (reverting those speakers to their default label) and MUST NOT delete any recordings or transcripts.

#### Scenario: Delete unlinks but preserves recordings

- **WHEN** the user deletes a Person
- **THEN** speakers linked to that Person revert to their default label
- **AND** the recordings and their transcripts remain intact
