## ADDED Requirements

### Requirement: Transcript is injected automatically into section prompts

When generating a summary, the system SHALL automatically supply the transcript to each section prompt so that template authors do not need to add a `{{transcript}}` placeholder manually. If a section prompt already references the transcript placeholder, the transcript MUST NOT be duplicated.

#### Scenario: Author omits the transcript placeholder

- **WHEN** a section prompt contains no transcript placeholder
- **THEN** the transcript is appended to that section's resolved prompt at summarize time

#### Scenario: Author includes the transcript placeholder

- **WHEN** a section prompt already contains the transcript placeholder
- **THEN** the transcript is substituted in place and not appended a second time

### Requirement: Templates have a general context

A summary template SHALL support an optional general-context text that describes the template's overall purpose, and the system SHALL prepend this context to each section prompt at summarize time.

#### Scenario: General context is applied to every section

- **WHEN** a template with a general context is used to summarize
- **THEN** each section's resolved prompt begins with the general context
- **AND** the transcript follows the section instruction

#### Scenario: Template without general context is unaffected

- **WHEN** a template has no general context
- **THEN** section prompts are resolved without an added context preamble

### Requirement: Template sections can be reordered by drag and drop

The template editor SHALL allow the user to reorder a template's sections by dragging, and the new order MUST be persisted.

#### Scenario: Reorder sections

- **WHEN** the user drags a section to a new position and saves
- **THEN** the template's section order reflects the new arrangement
- **AND** subsequent summaries use that order

### Requirement: Title and date placeholders are not advertised

The template editor SHALL NOT instruct users to use `{{title}}` or `{{date}}` placeholders, and SHALL remove guidance referencing them.

#### Scenario: Editor hint omits removed placeholders

- **WHEN** the user views the section prompt help text
- **THEN** it does not reference `{{title}}` or `{{date}}`
