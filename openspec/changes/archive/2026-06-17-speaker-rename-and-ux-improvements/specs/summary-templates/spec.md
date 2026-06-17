## MODIFIED Requirements

### Requirement: Summary templates have titled sections

A summary template SHALL consist of an ordered list of sections, each with a title and a prompt, stored as structured data (JSON). A template SHALL also support an optional general-context text describing the template's overall purpose, stored alongside the sections.

#### Scenario: Template defines multiple sections

- **WHEN** a summary template is created with sections "TL;DR", "Decisions", "Action items"
- **THEN** the template stores each section's title and prompt as ordered structured data

#### Scenario: Template stores general context

- **WHEN** a summary template is created with a general-context description
- **THEN** the general context is persisted with the template
- **AND** templates without one remain valid
