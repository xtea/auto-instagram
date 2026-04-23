from __future__ import annotations

from auto_instagram.publisher.profile import (
    captions_match,
    extract_caption_from_og,
    normalize_caption,
    shortcode_from_href,
)


def test_shortcode_from_href_post() -> None:
    assert shortcode_from_href("/nanorhino.ai/p/DXevxpmkaQ2/") == "DXevxpmkaQ2"


def test_shortcode_from_href_reel() -> None:
    assert shortcode_from_href("/someone/reel/ABC123xyz/") == "ABC123xyz"


def test_shortcode_from_href_bare() -> None:
    assert shortcode_from_href("/p/ABCDEF/") == "ABCDEF"


def test_shortcode_from_href_with_query() -> None:
    assert shortcode_from_href("/p/SC1/?utm=x") == "SC1"


def test_shortcode_from_href_none() -> None:
    assert shortcode_from_href(None) is None
    assert shortcode_from_href("") is None
    assert shortcode_from_href("/explore/") is None


def test_normalize_caption_collapses_whitespace_and_casefolds() -> None:
    assert normalize_caption("  Hello  World\n\nFoo\t") == "hello world foo"
    assert normalize_caption("FOO") == "foo"


def test_normalize_caption_none_and_empty() -> None:
    assert normalize_caption(None) == ""
    assert normalize_caption("   ") == ""


def test_captions_match_true_with_formatting_differences() -> None:
    a = "Hello world #tag\n\nNewline"
    b = "hello  world #tag\nnewline"
    assert captions_match(a, b)


def test_captions_match_false_on_different_content() -> None:
    assert not captions_match("a", "b")


def test_captions_match_false_when_one_empty() -> None:
    # Empty captions should never match — otherwise two empty-caption posts
    # would always be marked duplicates of each other.
    assert not captions_match("", "something")
    assert not captions_match(None, "something")
    assert not captions_match("", "")


def test_extract_caption_from_og_typical() -> None:
    og = (
        '0 likes, 0 comments - nanorhino.ai on April 23, 2026: '
        '"Testing auto-instagram end-to-end. First automated post from the new OSS publisher.\n'
        '#auto_instagram #opensource #test". '
    )
    cap = extract_caption_from_og(og)
    assert cap is not None
    assert cap.startswith("Testing auto-instagram")
    assert "#opensource" in cap


def test_extract_caption_from_og_none() -> None:
    assert extract_caption_from_og(None) is None
    assert extract_caption_from_og("") is None


def test_extract_caption_from_og_fallback() -> None:
    # If the quote-delimited format ever breaks, fall back to returning raw.
    assert extract_caption_from_og("plain string with no quotes") == (
        "plain string with no quotes"
    )


def test_match_works_against_extracted_og() -> None:
    incoming = (
        "Testing auto-instagram end-to-end. First automated post from the new OSS publisher.\n"
        "#auto_instagram #opensource #test"
    )
    og = (
        '0 likes, 0 comments - nanorhino.ai on April 23, 2026: '
        '"Testing auto-instagram end-to-end. First automated post from the new OSS publisher.\n'
        '#auto_instagram #opensource #test". '
    )
    extracted = extract_caption_from_og(og)
    assert captions_match(incoming, extracted)
