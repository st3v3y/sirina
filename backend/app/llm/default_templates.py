"""Seeded templates.

SUMMARY_TEMPLATES: built-in multi-section summary templates (SummaryTemplate).
QA_TEMPLATE: the single grounded Q&A prompt (PromptTemplate).
"""

SUMMARY_TEMPLATES = [
    {
        "name": "Standard meeting",
        "is_default": True,
        "builtin": True,
        "sections": [
            {"title": "TL;DR", "prompt": "Summarise the meeting in 2-3 sentences.\n\nTRANSCRIPT:\n{{transcript}}"},
            {"title": "Key decisions", "prompt": "List the concrete decisions made, as short bullets. If none, say 'None'.\n\nTRANSCRIPT:\n{{transcript}}"},
            {"title": "Action items", "prompt": "List action items as bullets, each with an owner and due date if mentioned. If none, say 'None'.\n\nTRANSCRIPT:\n{{transcript}}"},
            {"title": "Open questions", "prompt": "List unresolved questions or topics deferred, as short bullets. If none, say 'None'.\n\nTRANSCRIPT:\n{{transcript}}"},
        ],
    },
    {
        "name": "1:1",
        "is_default": False,
        "builtin": True,
        "sections": [
            {"title": "Highlights", "prompt": "Summarise the key points of this 1:1 conversation in a few bullets.\n\nTRANSCRIPT:\n{{transcript}}"},
            {"title": "Follow-ups", "prompt": "List agreed follow-ups and commitments, with owners. If none, say 'None'.\n\nTRANSCRIPT:\n{{transcript}}"},
            {"title": "Concerns", "prompt": "Note any concerns, blockers, or feedback raised. If none, say 'None'.\n\nTRANSCRIPT:\n{{transcript}}"},
        ],
    },
    {
        "name": "Standup",
        "is_default": False,
        "builtin": True,
        "sections": [
            {"title": "Done", "prompt": "What was reported as completed? Short bullets.\n\nTRANSCRIPT:\n{{transcript}}"},
            {"title": "Next", "prompt": "What is planned next? Short bullets.\n\nTRANSCRIPT:\n{{transcript}}"},
            {"title": "Blockers", "prompt": "List blockers raised, with who is affected. If none, say 'None'.\n\nTRANSCRIPT:\n{{transcript}}"},
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
