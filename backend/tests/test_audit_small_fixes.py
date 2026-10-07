"""Audit M7 (voice storage), M8 (restart word), M10 (login housekeeping and real mobile numbers)."""

from datetime import UTC, datetime, timedelta

import pytest

import app.voice as voice_module
from app import auth
from app import schemas as api
from app.voice import transcribe
from tests.test_voice import FakeVoiceClient, _FakeResponse, make_ids

# --- M8 ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("word", ["दोबारा", "शुरू", "शुरु", "  दोबारा. "])
def test_a_single_everyday_word_does_not_wipe_the_draft(word):
    assert api.parse_command(word) is None


@pytest.mark.parametrize(
    "text", ["दोबारा शुरू करो", "फिर से शुरू करो", "restart", "रीस्टार्ट", "शुरू से शुरू करो", "शुरू से"]
)
def test_real_restart_commands_still_work(text):
    assert api.parse_command(text) is api.Command.RESTART


def test_cancel_words_are_unchanged():
    assert api.parse_command("रद्द करो") is api.Command.CANCEL
    assert api.parse_command("रद्द मत करो") is None


# --- M7 ---------------------------------------------------------------------------------------------------


def test_a_storage_failure_still_transcribes_the_voice_note(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "k")
    monkeypatch.setenv("SARVAM_MODEL", "m")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("GROQ_WHISPER_MODEL", "w")
    monkeypatch.setenv("ASR_PIPELINE", "legacy")
    monkeypatch.setattr(voice_module.httpx, "post", lambda url, **kw: _FakeResponse({"transcript": "paani nahi aa raha"}))

    class BrokenStorage:
        def from_(self, _):
            return self

        def upload(self, *a, **k):
            raise RuntimeError("storage is down")

    client = FakeVoiceClient()
    client.storage = BrokenStorage()
    session_id, message_id = make_ids()

    result = transcribe(b"audio", "audio/webm", session_id, message_id, client=client)

    assert result.transcript == "paani nahi aa raha"
    assert result.audio_path is None  # the ticket is filed without a stored recording rather than not at all


# --- M10 --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("phone", ["9876543210", "+91 98765 43210", "6000000000", "09876543210"])
def test_real_indian_mobile_numbers_are_accepted(phone):
    assert auth.normalise_phone(phone).startswith("+91")


@pytest.mark.parametrize("phone", ["1234567890", "5123456789", "0123456789", "98765", "abcdefghij"])
def test_numbers_that_cannot_be_mobiles_are_refused(phone):
    with pytest.raises(auth.AuthError):
        auth.normalise_phone(phone)


def test_expired_challenges_are_purged_and_live_ones_kept():
    now = datetime.now(UTC)
    store = auth.MemoryAuthStore()
    old = store.create_challenge("+919876543210", "demo", now - timedelta(days=3))
    live = store.create_challenge("+919876543211", "demo", now + timedelta(minutes=5))
    store.delete_expired_challenges(now - timedelta(days=1))
    assert store.get_challenge(old) is None and store.get_challenge(live) is not None


def test_starting_a_login_sometimes_tidies_old_challenges_and_a_failure_never_blocks_it(monkeypatch):
    store = auth.MemoryAuthStore()
    service = auth.AuthService(store, auth.DemoProvider())
    stale = store.create_challenge("+919876543299", "demo", datetime.now(UTC) - timedelta(days=5))
    monkeypatch.setattr(auth.secrets, "randbelow", lambda n: 0)  # the 1-in-20 housekeeping turn
    service.start("9876543210")
    assert store.get_challenge(stale) is None

    def boom(_):
        raise RuntimeError("db down")

    store.delete_expired_challenges = boom
    assert service.start("9876543211").challenge_id  # still works
