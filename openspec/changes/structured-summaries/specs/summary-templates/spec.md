## ADDED Requirements

### Requirement: Summary templates have titled sections

A summary template SHALL consist of an ordered list of sections, each with a title and a prompt, stored as structured data (JSON).

#### Scenario: Template defines multiple sections

- **WHEN** a summary template is created with sections "TL;DR", "Decisions", "Action items"
- **THEN** the template stores each section's title and prompt as ordered structured data

### Requirement: Built-in templates are seeded and protected

The system SHALL seed a set of built-in summary templates on first run, and built-in templates MUST NOT be deletable.

#### Scenario: Built-ins available out of the box

- **WHEN** the application starts with no templates
- **THEN** built-in summary templates exist (e.g. a standard meeting template)

#### Scenario: Built-ins cannot be deleted

- **WHEN** a user attempts to delete a built-in template
- **THEN** the deletion is rejected

### Requirement: User templates are editable

The system SHALL allow creating, editing, and deleting non-built-in summary templates.

#### Scenario: Create and edit a custom template

- **WHEN** a user creates a custom summary template and edits its sections
- **THEN** the changes are persisted and usable for summarization
