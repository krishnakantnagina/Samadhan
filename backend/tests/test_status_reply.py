"""S29: complaint number parsing (typed and spoken forms), the status reply, and the route wiring."""

import pytest

from app import routes, status_reply, turn_engine, validator
from app.status_reply import build_status_reply, extract_complaint_id
from tests.test_routes import (  # noqa: F401
    SPEC,
    make_session_row,
    post,
    raise_if_called,
    test_client,
)

# ---------------------------------------------------------------------------------- parsing


@pytest.mark.parametrize(
    "text",
    [
        "SMD-0022",
        "smd-0022",
        "SMD 0022",
        "smd 22",
        "SMD22",
        "smd0022",
        "मेरी शिकायत SMD-0022 की स्थिति बताओ",
        "S M D 0 0 2 2",
        "s.m.d. 0022",
        "एसएमडी 0022",
        "एसएमडी 22",
        "एस एम डी 0022",
        "एस.एम.डी.-0022",
        "एसएमडी ००२२",  # Devanagari digits
        "एसएमडी शून्य शून्य दो दो",
    ],
)
def test_spoken_and_typed_forms_give_the_same_number(text):
    assert extract_complaint_id(text) == "SMD-0022"


def test_english_digit_words_and_mixed_forms():
    assert extract_complaint_id("smd zero zero two two") == "SMD-0022"
    assert extract_complaint_id("एसएमडी 0 0 3 4") == "SMD-0034"
    assert extract_complaint_id("SMD-12345") == "SMD-12345"  # more than 4 digits is kept
    assert extract_complaint_id("smd 7") == "SMD-0007"


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "बिजली नहीं आ रही",
        "मेरी शिकायत की स्थिति क्या है",  # no number
        "smd",  # prefix without a number
        "एसएमडी बताओ",
        "मेरे घर में 3 दिन से पानी नहीं आ रहा",  # a number that is not a complaint id
        "0022",  # bare number without the prefix (only accepted when the LLM said 'status')
        "यह बहुत लंबी शिकायत है जिसमें अंत में smd 22 लिखा है लेकिन बाकी सब कुछ इसी शिकायत के बारे में है और लंबा है",
    ],
)
def test_no_number_means_no_status_lookup(text):
    assert extract_complaint_id(text) is None


def test_a_bare_number_counts_only_when_the_llm_said_status():
    assert extract_complaint_id("मेरी शिकायत 22 की स्थिति", allow_bare=True) == "SMD-0022"
    assert (
        extract_complaint_id("मेरी शिकायत बाईस की स्थिति", allow_bare=True) is None
    )  # Hindi number word
    assert extract_complaint_id("स्थिति बताओ", allow_bare=True) is None


# ---------------------------------------------------------------------------------- reply text


def test_status_reply_shows_only_the_public_fields():
    row = {
        "status": "in_progress",
        "department": "Bijli Vibhag",
        "updated_at": "2026-09-29T13:50:51.879252Z",
    }
    reply = build_status_reply("SMD-0022", row)

    assert reply.split("\n") == [
        "आपकी शिकायत SMD-0022 की स्थिति: प्रक्रिया में है।",
        "विभाग: Bijli Vibhag।",
        "आखिरी अपडेट: 29-09-2026।",
    ]


@pytest.mark.parametrize("status", ["new", "in_progress", "resolved", "needs_review"])
def test_every_status_has_a_hindi_label(status):
    assert status in status_reply.STATUS_LABELS_HI
    assert status_reply.STATUS_LABELS_HI[status] in build_status_reply(
        "SMD-0001", {"status": status, "department": "X", "updated_at": "2026-09-29T00:00:00Z"}
    )


def test_unknown_number_gets_the_not_found_reply():
    assert "नहीं मिला" in build_status_reply("SMD-0099", None)


def test_a_bad_date_does_not_break_the_reply():
    assert "-।" in build_status_reply(
        "SMD-0001", {"status": "new", "department": "X", "updated_at": "junk"}
    )


# ---------------------------------------------------------------------------------- route wiring


def _patch_status(monkeypatch, row):
    monkeypatch.setattr(routes.ticketing, "get_status", lambda cid: row)


def test_a_message_with_a_number_is_answered_without_the_llm(test_client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(routes.turn_engine, "run_turn", raise_if_called)
    _patch_status(
        monkeypatch,
        {
            "status": "resolved",
            "department": "Jal Vibhag",
            "updated_at": "2026-09-28T08:10:00+00:00",
        },
    )
    saved = {}
    monkeypatch.setattr(routes.session, "save_turn", lambda **kw: saved.update(kw))

    body = post(test_client, text="SMD-0022").json()

    assert body["action"] == "out_of_scope"
    assert "SMD-0022" in body["reply_text"] and "हल हो चुकी है" in body["reply_text"]
    assert body["ticket"] is None and body["summary"] is None
    assert saved["session_update"].collected_fields == {}  # the session is left as it was


def test_a_spoken_number_works_through_the_transcript(test_client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(routes.turn_engine, "run_turn", raise_if_called)
    monkeypatch.setattr(
        routes.voice,
        "transcribe",
        lambda *a, **k: routes.voice.VoiceResult(
            transcript="एस एम डी शून्य शून्य दो दो", audio_path="s/m.webm"
        ),
    )
    _patch_status(
        monkeypatch,
        {"status": "new", "department": "Jal Vibhag", "updated_at": "2026-09-28T08:10:00+00:00"},
    )

    body = post(test_client, audio=b"fake").json()

    assert "SMD-0022" in body["reply_text"] and body["transcript"] == "एस एम डी शून्य शून्य दो दो"


def test_status_lookup_does_not_disturb_a_complaint_in_progress(test_client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(
        routes.session,
        "get_or_create_session",
        lambda sid: make_session_row(
            id=sid,
            service_id="water_supply",
            collected_fields={"issue_type": "no_supply"},
            awaiting_confirmation=True,
        ),
    )
    monkeypatch.setattr(routes.turn_engine, "run_turn", raise_if_called)
    _patch_status(
        monkeypatch,
        {"status": "new", "department": "Jal Vibhag", "updated_at": "2026-09-28T08:10:00+00:00"},
    )
    saved = {}
    monkeypatch.setattr(routes.session, "save_turn", lambda **kw: saved.update(kw))

    post(test_client, text="smd 22")

    update = saved["session_update"]
    assert update.collected_fields == {"issue_type": "no_supply"}
    assert update.awaiting_confirmation is True and update.service_id == "water_supply"


def test_unknown_number_reply(test_client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(routes.turn_engine, "run_turn", raise_if_called)
    _patch_status(monkeypatch, None)

    assert "नहीं मिला" in post(test_client, text="SMD-0099").json()["reply_text"]


def test_a_long_complaint_mentioning_a_number_is_not_hijacked(test_client, monkeypatch):  # noqa: F811
    called = []
    monkeypatch.setattr(
        routes.turn_engine,
        "run_turn",
        lambda **kw: (
            called.append(1) or turn_engine.TurnResult(service_id=None, fields={}, confirmed=False)
        ),
    )
    long_text = "मेरे घर में पानी बहुत दिनों से नहीं आ रहा है और मैंने पहले भी शिकायत की थी और अब फिर से smd 22 कहकर बता रहा हूँ"

    post(test_client, text=long_text)

    assert called == [1]


def test_llm_status_intent_with_a_bare_number_is_answered(test_client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(
        routes.turn_engine, "run_turn",
        lambda **kw: turn_engine.TurnResult(service_id=None, fields={}, confirmed=False, intent="status"),
    )  # fmt: skip
    _patch_status(
        monkeypatch,
        {"status": "new", "department": "Jal Vibhag", "updated_at": "2026-09-28T08:10:00+00:00"},
    )

    body = post(test_client, text="मेरी शिकायत 22 की स्थिति क्या है").json()

    assert "SMD-0022" in body["reply_text"]


def test_llm_status_intent_without_a_number_asks_for_it(test_client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(
        routes.turn_engine, "run_turn",
        lambda **kw: turn_engine.TurnResult(service_id=None, fields={}, confirmed=False, intent="status"),
    )  # fmt: skip
    monkeypatch.setattr(routes.ticketing, "get_status", raise_if_called)

    body = post(test_client, text="क्या मुझे अपनी शिकायत की स्थिति पता चलेगी").json()

    assert body["action"] == "out_of_scope"
    assert body["reply_text"] == status_reply.NEED_ID_REPLY_HI


def test_validator_status_intent_asks_for_the_number_and_keeps_the_session():
    from pathlib import Path

    from app.service_spec import load_specs

    specs = load_specs(Path(__file__).resolve().parents[2] / "specs")
    snap = validator.SessionSnapshot("water_supply", {"issue_type": "no_supply"}, False, None, None)
    result = validator.apply(
        specs=specs, session=snap,
        turn_result=turn_engine.TurnResult(service_id=None, fields={}, confirmed=False, intent="status"),
        lat=None, lng=None,
    )  # fmt: skip

    assert result.reply_text == status_reply.NEED_ID_REPLY_HI
    assert (
        result.collected_fields == {"issue_type": "no_supply"}
        and result.service_id == "water_supply"
    )


def test_a_status_question_that_carries_fields_is_still_a_complaint():
    from pathlib import Path

    from app.service_spec import load_specs

    specs = load_specs(Path(__file__).resolve().parents[2] / "specs")
    result = validator.apply(
        specs=specs, session=validator.SessionSnapshot(None, {}, False, None, None),
        turn_result=turn_engine.TurnResult(service_id="electricity", fields={"issue_type": "no_power"}, confirmed=False, intent="status"),
        lat=None, lng=None,
    )  # fmt: skip
    assert result.service_id == "electricity"
