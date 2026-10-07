"""Talk to a running backend like the website does: log in (demo PIN), send a complaint, and answer the bot's questions. Prints every turn and the routed office.

    uv run python scripts/try_complaint.py "mere gaon ke school me mid day meal nahi mil raha"            # answers questions automatically
    uv run python scripts/try_complaint.py --manual "msg 1" "msg 2" "haan"                                 # sends exactly these messages
    uv run python scripts/try_complaint.py --scenarios                                                      # one complaint per department

Options (env): API (default http://127.0.0.1:8000), PLACE (default Misrod), TEST_PHONE, TEST_PIN (demo 5555), PAUSE seconds between turns (default 4: the
free LLM tiers answer 429 when turns come too fast).
Use it with scripts/local_dev_server.py so tickets go to the private database, not the live one.
"""

import os
import sys
import time
import uuid

import httpx

API = os.environ.get("API", "http://127.0.0.1:8000").rstrip("/") + "/api/v1"
PHONE = os.environ.get("TEST_PHONE", "9000000001")
PLACE = os.environ.get("PLACE", "Misrod")
PAUSE = float(os.environ.get("PAUSE", "4"))

# (department id, complaint as a citizen would say it, an answer to "what exactly is the problem?")
SCENARIOS = [
    ("school_education", "mere gaon ke school me mid day meal nahi mil raha", "mid day meal nahi mil raha"),
    ("revenue", "patwari namantaran nahi kar raha aur paise maang raha hai", "namantaran ruka hua hai"),
    ("food_civil_supplies", "ration dukan wala ration nahi de raha", "ration nahi de raha"),
    ("public_health_family_welfare", "aspatal me doctor nahi aate dawai nahi milti", "doctor nahi aate"),
    ("panchayat_rural_development", "manrega ki majduri nahi mili sarpanch sunta nahi", "manrega majduri nahi mili"),
    ("social_justice_disabled", "budhapa pension nahi aa raha 4 mahine se", "vriddhavastha pension nahi mili"),
    ("home", "thane me FIR likhne se mana kar diya", "FIR darj nahi ho rahi"),
    ("women_child", "aanganwadi me poshan aahar nahi mil raha", "poshan aahar nahi mil raha"),
]


def login(c: httpx.Client) -> dict:
    start = c.post(f"{API}/auth/start", json={"phone": PHONE})
    if start.status_code == 503:  # login not enabled on this server: no token needed
        return {}
    start.raise_for_status()
    ok = c.post(f"{API}/auth/verify", json={"challenge_id": start.json()["challenge_id"], "code": os.environ.get("TEST_PIN", "5555")})
    ok.raise_for_status()
    return {"Authorization": f"Bearer {ok.json()['token']}"}


def send(c: httpx.Client, headers: dict, session: str, text: str) -> dict | None:
    for attempt in range(3):
        r = c.post(f"{API}/message", headers=headers, data={"session_id": session, "message_id": str(uuid.uuid4()), "text": text}, timeout=60)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 503 and attempt < 2:  # LLM rate limit: wait and try the same message again
            time.sleep(12)
            continue
        print(f"   ! HTTP {r.status_code}: {r.text[:160]}")
        return None
    return None


def auto_answer(body: dict, issue: str) -> str:
    """What a cooperative citizen would reply to each kind of question the bot asks."""
    ask = body["ask_for"] or ""
    if body["action"] == "confirm":
        return "haan"
    if ask == "service":
        return "haan"
    if ask == "location":
        return PLACE
    if ask == "location_detail":
        return "Bhopal, Huzur"
    if ask == "duration_days":
        return "5 din se"
    if ask in ("issue_type", "problem", "description"):
        return issue
    return "haan"


def converse(c: httpx.Client, headers: dict, first: str, issue: str, *, manual: list[str] | None = None) -> dict | None:
    session, last, text = str(uuid.uuid4()), None, first
    queue = list(manual or [])
    for _ in range(10):
        body = send(c, headers, session, text)
        if body is None:
            return last
        last = body
        print(f"  you> {text}\n  bot> [{body['action']}{'/' + body['ask_for'] if body['ask_for'] else ''}] {body['reply_text']}")
        if body["action"] in ("submitted", "cancelled"):
            return body
        if manual is not None:
            if not queue:
                return body
            text = queue.pop(0)
        else:
            text = auto_answer(body, issue)
        time.sleep(PAUSE)
    return last


def show(body: dict | None) -> None:
    t = (body or {}).get("ticket")
    print("   => " + (f"TICKET {t['complaint_id']} | department: {t['department']} | office: {t['office']['name']} ({t['office']['level']}) | status: {t['status']}" if t else "no ticket created"))


def main() -> None:
    args = sys.argv[1:]
    with httpx.Client() as c:
        headers = login(c)
        if args == ["--scenarios"]:
            for dept, complaint, issue in SCENARIOS:
                print(f"\n== {dept}")
                show(converse(c, headers, complaint, issue))
        elif args and args[0] == "--manual" and len(args) > 1:
            show(converse(c, headers, args[1], "", manual=args[2:]))
        elif args:
            show(converse(c, headers, " ".join(args), " ".join(args)))
        else:
            raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
