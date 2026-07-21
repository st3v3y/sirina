"""resegment_lines breaks monologue-sized lines into turns without touching normal ones."""
from app.processing.segment import resegment_lines
from app.transcribe.whisper import TLine


def test_short_line_unchanged():
    ln = TLine(0.0, 2.0, "Hi Stefan, how are you?")
    assert resegment_lines([ln]) == [ln]


def test_splits_on_long_pause_with_words():
    # Two utterances separated by a 2s pause; each long enough to stand alone.
    words = [
        (0.0, 0.5, "Hello"), (0.5, 1.0, "there"), (1.0, 1.5, "everyone"),
        (1.5, 2.0, "welcome"), (2.0, 2.5, "aboard"), (2.5, 3.0, "today."),
        # 2s silence here →
        (5.0, 5.5, "Now"), (5.5, 6.0, "let's"), (6.0, 6.5, "get"),
        (6.5, 7.0, "started"), (7.0, 7.5, "properly"), (7.5, 8.0, "here."),
    ]
    ln = TLine(0.0, 8.0, " ".join(w[2] for w in words), words)
    out = resegment_lines([ln])
    assert len(out) == 2
    assert out[0].text.startswith("Hello")
    assert out[1].text.startswith("Now")
    assert out[1].start >= 5.0  # second piece begins after the pause


def test_hard_duration_cap_with_words():
    # 20 words, 1s each, no pauses, no sentence ends → must still break at the hard cap.
    words = [(float(i), float(i + 1), f"word{i}") for i in range(20)]
    ln = TLine(0.0, 20.0, " ".join(w[2] for w in words), words)
    out = resegment_lines([ln])
    assert len(out) >= 2
    for piece in out:
        assert piece.end - piece.start <= 16.0 + 1.0


def test_sentence_split_without_words():
    text = (
        "This is the first fairly long sentence that carries some real content. "
        "Here is a second sentence that also has a good amount of words in it. "
        "And a third one to make sure we cross the length threshold comfortably."
    )
    ln = TLine(0.0, 30.0, text)  # long duration, no word timestamps
    out = resegment_lines([ln])
    assert len(out) == 3
    assert out[0].start == 0.0
    assert out[-1].end == 30.0
    # timestamps stay monotonic and non-overlapping
    for a, b in zip(out, out[1:]):
        assert a.end <= b.start + 1e-6


def test_no_sentence_boundaries_stays_single():
    ln = TLine(0.0, 30.0, "word " * 60)  # long but unsplittable (no punctuation)
    out = resegment_lines([ln])
    assert len(out) == 1
