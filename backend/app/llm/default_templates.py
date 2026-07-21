"""Seeded templates.

SUMMARY_TEMPLATES: built-in multi-section summary templates (SummaryTemplate).
QA_TEMPLATE: the single grounded Q&A prompt (PromptTemplate).

Built-in summary templates are refreshed from code on startup (db.init_db), so edits
here reach existing installs. The Q&A prompt is user-editable, so it is only refreshed
when the stored body is an unmodified previous default (see _LEGACY_QA_BODIES).
"""

# Section prompts deliberately DON'T include the transcript: the pipeline auto-appends it
# (see Pipeline.summarize) when a section omits the {{transcript}} placeholder, so keeping
# the prompts clean here also keeps the template editor readable.
SUMMARY_TEMPLATES = [
    {
        "name": "Standard meeting",
        "is_default": True,
        "builtin": True,
        "sections": [
            {
                "title": "TL;DR",
                "prompt": (
                    "Write 2-4 sentences of plain prose (no bullets). The first sentence names "
                    "who met and what about — e.g. 'A meeting between Anna and Ben about the Q3 "
                    "launch.' The rest give the most important outcomes and decisions. Be "
                    "specific: use names, numbers, and dates from the transcript."
                ),
            },
            {
                "title": "Attendees",
                "prompt": (
                    "List everyone who took part, one per line as '- Name — role or affiliation "
                    "(only if stated)'. Use the speaker names from the transcript; when a real "
                    "name is clearly stated for a generic speaker label, use the real name. "
                    "Never invent people or roles. If a speaker can't be identified, write "
                    "'- Unknown speaker'."
                ),
            },
            {
                "title": "Agenda & topics",
                "prompt": (
                    "List the main topics actually discussed, as short bullets in the order they "
                    "came up. One concise line per topic. Skip greetings, small talk, and "
                    "logistics unless they mattered."
                ),
            },
            {
                "title": "Key decisions",
                "prompt": (
                    "List every decision that was actually made — something settled or agreed, "
                    "not merely discussed. One bullet per decision: what was decided, plus who "
                    "decided or the stated reason when the transcript gives one. Proposals that "
                    "stayed open belong in 'Open questions', not here. If none, output exactly: "
                    "None."
                ),
            },
            {
                "title": "Action items",
                "prompt": (
                    "List every task someone committed to, one bullet each in the form "
                    "'- **Owner**: task (due: date)'. Omit '(due: …)' when no deadline was "
                    "mentioned; use '**Unassigned**' when nobody took the task. Only include "
                    "tasks the transcript supports. If none, output exactly: None."
                ),
            },
            {
                "title": "Open questions",
                "prompt": (
                    "List unresolved questions, points of disagreement, and topics explicitly "
                    "parked for later, as short bullets. If none, output exactly: None."
                ),
            },
            {
                "title": "Next steps",
                "prompt": (
                    "List agreed follow-ups that are not individual action items — the next "
                    "meeting, milestones, things being waited on from outside. Short bullets. "
                    "Don't repeat the Action items section. If none, output exactly: None."
                ),
            },
        ],
    },
    {
        "name": "1:1",
        "is_default": False,
        "builtin": True,
        "sections": [
            {
                "title": "Highlights",
                "prompt": (
                    "Summarise the key points of this 1:1 in 3-6 bullets, most important first. "
                    "Be specific about what was said and by whom."
                ),
            },
            {
                "title": "Follow-ups",
                "prompt": (
                    "List commitments and follow-ups, one bullet each as '- **Owner**: task "
                    "(due: date)'; omit '(due: …)' when no deadline was mentioned. If none, "
                    "output exactly: None."
                ),
            },
            {
                "title": "Concerns",
                "prompt": (
                    "Note concerns, blockers, or feedback raised — who raised it and what it is "
                    "about, as short bullets. If none, output exactly: None."
                ),
            },
        ],
    },
    {
        "name": "Standup",
        "is_default": False,
        "builtin": True,
        "sections": [
            {
                "title": "Done",
                "prompt": (
                    "What did each person report as completed? One bullet per item as "
                    "'- **Name**: what was finished'."
                ),
            },
            {
                "title": "Next",
                "prompt": (
                    "What is each person planning next? One bullet per item as "
                    "'- **Name**: what they'll do'."
                ),
            },
            {
                "title": "Blockers",
                "prompt": (
                    "List blockers as '- **Name**: blocker — what or who is needed to unblock'. "
                    "If none, output exactly: None."
                ),
            },
        ],
    },
]

QA_TEMPLATE = {
    "name": "Q&A grounded",
    "is_default": True,
    "body": """You answer questions about one meeting, grounded strictly in its transcript.

RULES:
- Use ONLY the transcript and the prior Q&A below. If the answer isn't in the transcript, say so plainly — never guess and never use outside knowledge.
- Lead with the answer, then add brief supporting detail. Mention who said something when it matters.
- Be concise. Use bullets only when listing several items.
- Answer in the language the question was asked in.
- No preamble or meta-commentary — never restate that you are reading a transcript.

TRANSCRIPT:
{{transcript}}

PRIOR Q&A:
{{qa_history}}

QUESTION:
{{question}}

ANSWER:""",
}

# Previous default Q&A bodies, verbatim. If the stored prompt matches one of these the
# user never customised it, so init_db upgrades it to the current QA_TEMPLATE body.
_LEGACY_QA_BODIES = [
    """You are a helpful assistant answering questions about a meeting. Use ONLY the transcript and prior Q&A history below. If the answer isn't supported by the transcript, say so.

TRANSCRIPT:
{{transcript}}

PRIOR Q&A:
{{qa_history}}

QUESTION:
{{question}}

ANSWER:""",
]
