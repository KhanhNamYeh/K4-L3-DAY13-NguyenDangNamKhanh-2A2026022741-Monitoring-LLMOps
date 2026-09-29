from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd() -> None:
    out = scrub_text("CCCD cua toi la 001203004567.")
    assert "001203004567" not in out
    assert "REDACTED_CCCD" in out


def test_scrub_credit_card_formats() -> None:
    cards = (
        "4111111111111111",
        "4111 1111 1111 1111",
        "4111-1111-1111-1111",
    )

    for card in cards:
        out = scrub_text(f"Card: {card}")
        assert card not in out
        assert "REDACTED_CREDIT_CARD" in out
        assert "REDACTED_PHONE_VN" not in out


def test_scrub_multiple_pii_in_one_message() -> None:
    message = (
        "Email student@vinuni.edu.vn, phone 0987654321, "
        "CCCD 001203004567, card 4111 1111 1111 1111"
    )
    out = scrub_text(message)
    for raw in ("student@vinuni.edu.vn", "0987654321", "001203004567", "4111 1111 1111 1111"):
        assert raw not in out
    for label in ("EMAIL", "PHONE_VN", "CCCD", "CREDIT_CARD"):
        assert f"REDACTED_{label}" in out


def test_scrub_keeps_non_pii_text() -> None:
    text = "req-1a2b3c4d latency 1200ms, P95 under 3000 ms in 2026"
    assert scrub_text(text) == text
