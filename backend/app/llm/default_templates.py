DEFAULT_TEMPLATES = [
    {
        "name": "Aspects (live)",
        "kind": "aspects",
        "is_default": True,
        "body": """You are a meeting note-taker. Given the previous bullet list (may be empty) and the NEW transcript chunk, return an UPDATED bullet list of 3-8 short bullets ("aspects") that capture the live state of the discussion. Revise prior bullets if context changes them; keep them terse (<= 12 words each). No preamble.

PREVIOUS ASPECTS:
{{previous_aspects}}

NEW TRANSCRIPT:
{{new_transcript}}

UPDATED ASPECTS (bullets only):""",
    },
    {
        "name": "Standard summary",
        "kind": "summary",
        "is_default": True,
        "body": """Summarise the meeting transcript below. Output sections:
- TL;DR (2-3 sentences)
- Key decisions
- Action items (with owner if mentioned)
- Open questions

TRANSCRIPT:
{{transcript}}""",
    },
    {
        "name": "Q&A grounded",
        "kind": "qa",
        "is_default": True,
        "body": """You are a helpful assistant answering questions about a meeting. Use ONLY the transcript and prior Q&A history below. If the answer isn't supported by the transcript, say so.

TRANSCRIPT:
{{transcript}}

PRIOR Q&A:
{{qa_history}}

QUESTION:
{{question}}

ANSWER:""",
    },
]
