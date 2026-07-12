"""Seeded templates.

SUMMARY_TEMPLATES: built-in multi-section summary templates (SummaryTemplate).
QA_TEMPLATE: the single grounded Q&A prompt (PromptTemplate).
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
            {"title": "TL;DR", "prompt": "Summarise the meeting in 2-3 sentences."},
            {"title": "Attendees", "prompt": "List who took part, one per line, using the speaker names/labels in the transcript (use a real name when one is clearly stated for a speaker). Do not invent people. If unclear, say 'Unknown'."},
            {"title": "Agenda & topics", "prompt": "List the main topics discussed, as short bullets, in the order they came up."},
            {"title": "Key decisions", "prompt": "List the concrete decisions made, as short bullets. If none, say 'None'."},
            {"title": "Action items", "prompt": "List action items as bullets, each with an owner and a due date if mentioned. If none, say 'None'."},
            {"title": "Open questions", "prompt": "List unresolved questions or topics deferred, as short bullets. If none, say 'None'."},
            {"title": "Next steps", "prompt": "List agreed next steps and any planned follow-up, as short bullets. If none, say 'None'."},
        ],
    },
    {
        "name": "1:1",
        "is_default": False,
        "builtin": True,
        "sections": [
            {"title": "Highlights", "prompt": "Summarise the key points of this 1:1 conversation in a few bullets."},
            {"title": "Follow-ups", "prompt": "List agreed follow-ups and commitments, with owners. If none, say 'None'."},
            {"title": "Concerns", "prompt": "Note any concerns, blockers, or feedback raised. If none, say 'None'."},
        ],
    },
    {
        "name": "Standup",
        "is_default": False,
        "builtin": True,
        "sections": [
            {"title": "Done", "prompt": "What was reported as completed? Short bullets."},
            {"title": "Next", "prompt": "What is planned next? Short bullets."},
            {"title": "Blockers", "prompt": "List blockers raised, with who is affected. If none, say 'None'."},
        ],
    },
]

QA_TEMPLATE = {
    "name": "Q&A grounded",
    "is_default": True,
    "body": """You are a helpful assistant answering questions about a meeting. Use ONLY the transcript and prior Q&A history below. If the answer isn't supported by the transcript, say so.

TRANSCRIPT:
{{transcript}}

PRIOR Q&A:
{{qa_history}}

QUESTION:
{{question}}

ANSWER:""",
}
