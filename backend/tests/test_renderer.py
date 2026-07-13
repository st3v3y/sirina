from app.llm.provider import render


def test_render_substitutes_known_placeholders():
    out = render("Hi {{name}}, transcript:\n{{transcript}}", {"name": "Bob", "transcript": "..."})
    assert out == "Hi Bob, transcript:\n..."


def test_render_leaves_unknown_placeholders_untouched():
    out = render("{{a}} - {{b}}", {"a": "x"})
    assert out == "x - {{b}}"


def test_render_repeats_same_key():
    out = render("{{x}}-{{x}}", {"x": "1"})
    assert out == "1-1"


def test_render_with_no_vars():
    assert render("plain text", {}) == "plain text"
