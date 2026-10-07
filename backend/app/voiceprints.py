"""Voice fingerprints: match a recording's diarized speakers to known People.

Diarization yields one embedding (speaker centroid) per cluster; we store it on the
Speaker row. When the user renames a speaker to a real Person, that embedding is
enrolled into the Person's voiceprint (a running mean). Future recordings compare
their speakers' embeddings against all enrolled voiceprints (cosine similarity) and
auto-link matches above `settings.voice_match_threshold`.

Only manual renames enroll — automatic matches never update a voiceprint, so a wrong
match can be fixed with a rename and can't compound over time.
"""
from __future__ import annotations

import json
import logging
import math

from sqlmodel import Session, select

from .config import settings
from .models import Person, Speaker

log = logging.getLogger(__name__)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def decode(raw: str | None) -> list[float] | None:
    """A stored embedding/voiceprint JSON column -> float list (None if absent/invalid)."""
    if not raw:
        return None
    try:
        vec = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(vec, list) or not vec:
        return None
    try:
        return [float(x) for x in vec]
    except (TypeError, ValueError):
        return None


def enroll(person: Person, embedding: list[float], model: str | None = None) -> None:
    """Merge a manually-confirmed speaker embedding into the person's voiceprint
    (running mean over all enrollments). A different embedding model or a dimension
    mismatch discards the old voiceprint and starts over."""
    from .processing.diarize import VOICEPRINT_MODEL

    model = model or VOICEPRINT_MODEL
    emb = [float(x) for x in embedding]
    cur = decode(person.voiceprint)
    n = person.voiceprint_n or 0
    if cur is None or len(cur) != len(emb) or n <= 0 or person.voiceprint_model != model:
        person.voiceprint = json.dumps(emb)
        person.voiceprint_n = 1
        person.voiceprint_model = model
        return
    person.voiceprint = json.dumps([(c * n + e) / (n + 1) for c, e in zip(cur, emb)])
    person.voiceprint_n = n + 1


def withdraw(person: Person, embedding: list[float]) -> None:
    """Remove one previously-enrolled sample from the person's voiceprint (inverse of
    `enroll`, exact for a running mean). Used when the user corrects a wrong rename so
    the mis-attributed sample doesn't keep polluting the fingerprint. A dimension
    mismatch means the sample never contributed to the current voiceprint — no-op."""
    emb = [float(x) for x in embedding]
    cur = decode(person.voiceprint)
    n = person.voiceprint_n or 0
    if cur is None or len(cur) != len(emb) or n <= 0:
        return
    if n == 1:
        person.voiceprint = None
        person.voiceprint_n = 0
        return
    person.voiceprint = json.dumps([(c * n - e) / (n - 1) for c, e in zip(cur, emb)])
    person.voiceprint_n = n - 1


def match_speakers(session: Session, recording_id: int) -> list[tuple[int, int]]:
    """Auto-link this recording's unlinked, embedded speakers to known People by
    voiceprint similarity. Greedy best-match-first; each speaker and each person is
    used at most once (two speakers in one meeting can't both be the same person).
    Never creates People. Returns the (speaker_id, person_id) pairs linked."""
    threshold = settings.voice_match_threshold
    if threshold <= 0:
        return []
    from .processing.diarize import VOICEPRINT_MODEL

    speakers = session.exec(select(Speaker).where(Speaker.recording_id == recording_id)).all()
    candidates = [
        (sp, vec)
        for sp in speakers
        if sp.person_id is None
        and sp.embedding_model == VOICEPRINT_MODEL
        and (vec := decode(sp.embedding)) is not None
    ]
    if not candidates:
        return []
    people = [
        (p, vec)
        for p in session.exec(select(Person)).all()
        if not p.is_self
        and p.voiceprint_model == VOICEPRINT_MODEL
        and (vec := decode(p.voiceprint)) is not None
    ]
    if not people:
        return []

    scored: list[tuple[float, Speaker, Person]] = []
    for sp, sp_vec in candidates:
        for person, p_vec in people:
            sim = cosine_similarity(sp_vec, p_vec)
            if sim >= threshold:
                scored.append((sim, sp, person))
    scored.sort(key=lambda t: t[0], reverse=True)

    linked: list[tuple[int, int]] = []
    used_speakers: set[int] = set()
    used_people: set[int] = set()
    for sim, sp, person in scored:
        assert sp.id is not None and person.id is not None
        if sp.id in used_speakers or person.id in used_people:
            continue
        sp.person_id = person.id
        session.add(sp)
        used_speakers.add(sp.id)
        used_people.add(person.id)
        linked.append((sp.id, person.id))
        log.info(
            "voice match: recording %d speaker %r -> %s (similarity %.2f)",
            recording_id, sp.label, person.name, sim,
        )
    if linked:
        session.commit()
    return linked
