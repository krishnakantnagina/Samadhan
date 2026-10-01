"""Synthetic DEMO tickets (default 360) so the CM-office dashboard can be explored and analysed before real volume exists.

EVERYTHING HERE IS INVENTED. It is generated (seeded, reproducible), never written to Supabase, and every row carries is_demo=True and a
`DEMO-` complaint id; the app shows a visible DEMO badge whenever this dataset is on screen. Real inputs only where they are real: the 55 district
names, their divisions and 2011 populations come from the scraped registry (mpinfo.org). Complaint types per department are plausible everyday
grievances, not counts from any real system. Volumes, dates, statuses and hotspots are fabricated on purpose so that area analysis has something to find.

Run `uv run python -m dashboard.cm.demo_data` to also export local-research/data/demo_tickets.csv (git-excluded).
"""

import math
import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pandas as pd

from dashboard.cm.departments import LIVE_MAP

# registry id -> [(issue, weight, typical days to resolve)]
ISSUES: dict[str, list[tuple[str, float, float]]] = {
    "phe": [("No water supply", 5, 6), ("Handpump not working", 6, 8), ("Dirty or smelly water", 3, 7), ("Pipeline leakage", 3, 9), ("Low water pressure", 2, 6)],
    "energy": [("Power cut for days", 5, 3), ("Transformer failed", 3, 6), ("Low or high voltage", 3, 5), ("Wrong electricity bill", 3, 9), ("Pole or wire hanging", 2, 4)],
    "public_works": [("Potholes on road", 5, 18), ("Broken culvert or bridge", 2, 30), ("Damaged road after rain", 3, 24)],
    "urban_development_housing": [("Garbage not collected", 5, 4), ("Drain blocked or overflowing", 4, 6), ("Streetlight not working", 3, 8), ("Dirty public area", 2, 5)],
    "home": [("Theft report not registered", 2, 10), ("Cyber fraud complaint", 3, 14), ("Loud noise nuisance", 1, 3)],
    "food_civil_supplies": [("Ration shop gives less grain", 4, 9), ("Ration card correction pending", 3, 16)],
    "public_health_family_welfare": [("Doctor absent at health centre", 3, 7), ("Medicine not available", 3, 6), ("Ambulance delayed", 2, 2)],
    "school_education": [("Teacher absent from school", 3, 10), ("Mid-day meal quality poor", 3, 6), ("School building needs repair", 2, 40)],
    "revenue": [("Land record error", 3, 25), ("Mutation delayed", 3, 30), ("Income or domicile certificate delayed", 3, 12)],
    "social_justice_disabled": [("Pension not received", 5, 15), ("Disability certificate delayed", 2, 20)],
    "agriculture": [("Seed or fertiliser shortage", 3, 8), ("Crop insurance claim pending", 3, 35)],
    "animal_husbandry": [("Cattle vaccination not done", 2, 7), ("Cattle disease outbreak", 1, 3)],
    "women_child": [("Anganwadi not opening", 3, 9), ("Nutrition supply not reaching", 2, 11)],
    "transport": [("Bus service stopped", 2, 20), ("Driving licence delayed", 2, 18)],
    "panchayat_rural_development": [("MGNREGA wages pending", 5, 22), ("Village road in poor condition", 3, 28), ("Nal-jal connection not working", 3, 14)],
    "labour": [("Wages not paid", 2, 14), ("Labour card not issued", 2, 18)],
    "forest": [("Wild animal damaging crops", 2, 12)],
    "tribal_affairs": [("Scholarship not received", 2, 26)],
    "general_administration": [("Caste certificate delayed", 4, 14)],
    "cooperative": [("Society loan not sanctioned", 1, 25)],
}
# relative share of all complaints per department (water/power/roads/sanitation dominate everyday grievances)
DEPT_WEIGHT = {"phe": 20, "energy": 13, "public_works": 8, "urban_development_housing": 10, "home": 4, "food_civil_supplies": 5, "public_health_family_welfare": 5,
               "school_education": 5, "revenue": 6, "social_justice_disabled": 4, "agriculture": 4, "animal_husbandry": 2, "women_child": 2, "transport": 2,
               "panchayat_rural_development": 6, "labour": 1.5, "forest": 1, "tribal_affairs": 1, "general_administration": 1.5, "cooperative": 0.5}
# planted on purpose so there is something to find: (district, issue, number of recent tickets). Generated as a cluster in the last ~4 weeks.
HOTSPOTS = [("Sagar", "Handpump not working", 7), ("Rewa", "Power cut for days", 6), ("Chhatarpur", "MGNREGA wages pending", 6),
            ("Dindori", "Potholes on road", 5), ("Indore", "Garbage not collected", 5), ("Shivpuri", "No water supply", 5)]
ISSUE_DEPT = {issue: dept for dept, items in ISSUES.items() for issue, _w, _d in items}

# Invented citizen messages (Hindi / dialect-style) for the demo; one per issue. Not from any real complaint.
ISSUE_HI = {
    "No water supply": "हमाए गाँव में पानी नईं आ रओ", "Handpump not working": "हैंडपंप खराब पड़ो है, पानी नईं निकल रओ", "Dirty or smelly water": "नल में गंदो पानी आ रओ है",
    "Pipeline leakage": "पाइपलाइन फूटी है, पानी बह रओ", "Low water pressure": "नल में पानी बहुत धीरे आत है",
    "Power cut for days": "तीन दिन से बिजली नईं है", "Transformer failed": "ट्रांसफार्मर जल गओ, पूरो मोहल्ला अँधेरे में", "Low or high voltage": "बिजली कम-ज्यादा आत है, पंखो नईं चलत",
    "Wrong electricity bill": "बिजली को बिल गलत आओ है", "Pole or wire hanging": "खंभा झुको है, तार लटक रओ",
    "Potholes on road": "सड़क पे बड़े-बड़े गड्ढे हैं", "Broken culvert or bridge": "पुलिया टूट गई है", "Damaged road after rain": "बारिश के बाद सड़क खराब हो गई",
    "Garbage not collected": "कचरा गाड़ी नईं आ रई, कचरा पड़ो है", "Drain blocked or overflowing": "नाली जाम है, पानी सड़क पे बह रओ", "Streetlight not working": "गली की लाइट बंद है",
    "Dirty public area": "मोहल्ले में गंदगी फैली है",
    "Theft report not registered": "चोरी की रिपोर्ट थाने में नईं लिख रए", "Cyber fraud complaint": "खाते से ऑनलाइन ठगी हो गई", "Loud noise nuisance": "रात भर तेज आवाज में डीजे बजत है",
    "Ration shop gives less grain": "राशन दुकान वाला कम अनाज दे रओ", "Ration card correction pending": "राशन कार्ड में नाम सुधार नईं भओ",
    "Doctor absent at health centre": "अस्पताल में डॉक्टर साहब नईं मिलत", "Medicine not available": "दवाई नईं मिल रई", "Ambulance delayed": "एम्बुलेंस बहुत देर से आई",
    "Teacher absent from school": "स्कूल में मास्टर साहब नईं आत", "Mid-day meal quality poor": "मिड-डे मील को खाना खराब है", "School building needs repair": "स्कूल की छत टपकत है",
    "Land record error": "जमीन के रिकार्ड में नाम गलत चढ़ो है", "Mutation delayed": "नामांतरण महीनों से अटको है", "Income or domicile certificate delayed": "आय प्रमाण पत्र नईं बन रओ",
    "Pension not received": "पेंशन छह महीने से नईं आई", "Disability certificate delayed": "दिव्यांग प्रमाण पत्र नईं बन रओ",
    "Seed or fertiliser shortage": "खाद-बीज नईं मिल रओ", "Crop insurance claim pending": "फसल बीमा को पैसा नईं आओ",
    "Cattle vaccination not done": "मवेशियन को टीको नईं लगो", "Cattle disease outbreak": "गाय-भैंसन में बीमारी फैल रई",
    "Anganwadi not opening": "आंगनवाड़ी रोज नईं खुलत", "Nutrition supply not reaching": "पोषण आहार नईं मिल रओ",
    "Bus service stopped": "गाँव की बस बंद हो गई", "Driving licence delayed": "ड्राइविंग लाइसेंस नईं आओ",
    "MGNREGA wages pending": "मनरेगा की मजदूरी नईं मिली", "Village road in poor condition": "गाँव की सड़क बहुत खराब है", "Nal-jal connection not working": "नल-जल योजना को नल चालू नईं भओ",
    "Wages not paid": "ठेकेदार ने मजदूरी नईं दी", "Labour card not issued": "श्रमिक कार्ड नईं बन रओ", "Wild animal damaging crops": "जंगली जानवर फसल खराब कर रए",
    "Scholarship not received": "छात्रवृत्ति को पैसा नईं आओ", "Caste certificate delayed": "जाति प्रमाण पत्र नईं बन रओ", "Society loan not sanctioned": "सोसायटी से लोन नईं मिल रओ",
}
# departments a model plausibly confuses with each other (used for the demo's "Jev was unsure between ..." rows)
RELATED = {"phe": ["panchayat_rural_development", "urban_development_housing"], "public_works": ["panchayat_rural_development", "urban_development_housing"],
           "urban_development_housing": ["panchayat_rural_development", "public_works"], "panchayat_rural_development": ["labour", "public_works"],
           "school_education": ["higher_education", "tribal_affairs"], "tribal_affairs": ["school_education", "sc_welfare"], "social_justice_disabled": ["sc_welfare", "women_child"],
           "home": ["finance", "general_administration"], "revenue": ["general_administration", "agriculture"], "agriculture": ["horticulture_food_processing", "cooperative"]}
EVAL_REASONS = [("department_unconfirmed", 0.55), ("location_unclear", 0.30), ("vague_description", 0.15)]
HUMAN_EVALUATORS = ["evaluator.desk"]
ISSUE_DAYS = {issue: d for items in ISSUES.values() for issue, _w, d in items}
LIVE_OFFICE_BY_DEPT = {"Jal Vibhag": "Ward मिसरोद Office", "Bijli Vibhag": "Ward मिसरोद Bijli Office (DEMO)",
                       "Lok Nirman Vibhag": "Ward मिसरोद PWD Office (DEMO)", "Nagar Nigam Sanitation": "Ward मिसरोद Sanitation Office (DEMO)"}
QUALITY = [("exact", 0.18), ("village", 0.52), ("district", 0.24), ("unknown", 0.06)]
URBAN_DISTRICTS = {"Bhopal", "Indore", "Jabalpur", "Gwalior", "Ujjain", "Sagar", "Rewa", "Satna", "Ratlam", "Dewas"}


def _department_text(dept_id: str, names: dict[str, str]) -> str:
    """The department string a ticket carries: Samadhan's own name for the 4 live ones, else the registry's English name."""
    live = next((k for k, v in LIVE_MAP.items() if v == dept_id), None)
    return live or names.get(dept_id, dept_id)


def generate(districts: Sequence[dict], names: dict[str, str], n: int = 360, seed: int = 2026, now: datetime | None = None, days: int = 90) -> pd.DataFrame:
    """`districts`: dicts with name, division, population_2011 (registry rows). `names`: registry id -> English name. Deterministic for a given seed and `now`."""
    if not districts:
        raise ValueError("generate() needs the district list from the registry")
    rng = random.Random(seed)
    now = now or datetime.now(UTC)
    pop = {d["name"]: float(d["population_2011"] or 1_000_000) for d in districts}
    division = {d["name"]: d["division"] for d in districts}
    dept_ids = list(DEPT_WEIGHT)
    weights = {d: pop[d] ** 0.9 for d in pop}

    def make(dept_id: str, issue: str, mean_days: float, district: str, age: float) -> dict:
        created = now - timedelta(days=age, minutes=rng.randint(0, 600))
        p_resolved = min(0.88, 0.12 + age / 110)
        if rng.random() < p_resolved:
            status = "resolved"
            took = min(max(age - 0.05, 0.05), max(0.2, rng.lognormvariate(math.log(mean_days), 0.55)))
            updated = created + timedelta(days=took)
        else:
            status = "needs_review" if rng.random() < 0.11 else ("in_progress" if rng.random() < 0.42 else "new")
            updated = created + timedelta(hours=rng.randint(1, 72))
        updated = min(updated, now)
        department = _department_text(dept_id, names)
        office = LIVE_OFFICE_BY_DEPT.get(department) if district == "Bhopal" and rng.random() < 0.6 else None
        quality = rng.choices([q for q, _ in QUALITY], [w for _, w in QUALITY])[0]
        needs_human = status == "needs_review"
        evaluated = (not needs_human) and rng.random() < 0.14  # a person confirmed the department earlier
        reason = rng.choices([r for r, _ in EVAL_REASONS], [w for _, w in EVAL_REASONS])[0] if (needs_human or evaluated) else ""
        rel = RELATED.get(dept_id) or rng.sample([d for d in dept_ids if d != dept_id], 2)
        second_id = rng.choice(rel)
        if reason == "department_unconfirmed":
            top_p = round(rng.uniform(0.38, 0.62), 2)
        elif reason:
            top_p = round(rng.uniform(0.78, 0.96), 2)
        else:
            top_p = round(rng.uniform(0.86, 1.0), 2)
        jev_wrong = evaluated and reason == "department_unconfirmed" and rng.random() < 0.35  # humans sometimes overrule the model's first choice
        jev_top_id = second_id if jev_wrong else dept_id
        jev_second_id = dept_id if jev_wrong else second_id
        sits_in_triage = needs_human and reason == "department_unconfirmed"
        if sits_in_triage:
            department, office = "Human Evaluation", "Human Evaluation Desk (DEMO)"
        else:
            office = office or f"{department} office, {district} (demo)"
        return {
            "created_at": created.isoformat(timespec="seconds"), "updated_at": updated.isoformat(timespec="seconds"),
            "status": status, "department": department, "dept_id": "human_evaluation" if sits_in_triage else dept_id, "office_name": office,
            "issue": issue, "district": district, "division": division[district],
            "area_type": "urban" if district in URBAN_DISTRICTS and rng.random() < 0.7 else "rural", "location_quality": quality,
            "citizen_message": ISSUE_HI.get(issue, issue), "eval_reason": reason,
            "questions_asked": (rng.randint(1, 2) if reason == "department_unconfirmed" else rng.randint(1, 3)) if reason else rng.randint(0, 2),
            "jev_top": _department_text(jev_top_id, names), "jev_top_p": top_p,
            "jev_second": _department_text(jev_second_id, names), "jev_second_p": round(min(1 - top_p, rng.uniform(0.2, 0.45) if reason == "department_unconfirmed" else 1 - top_p), 2),
            "duration_days": rng.choice([1, 2, 3, 5, 7, 10, 15]) if rng.random() < 0.7 else None,
            "evaluated_by": rng.choice(HUMAN_EVALUATORS) if evaluated else "", "evaluated_dept": department if evaluated else "",
            "summary_en": f"Issue: {issue}; District: {district}" + (f"; Days affected: {rng.choice([1, 2, 3, 5, 7, 10, 15])}" if rng.random() < 0.7 else ""),
        }

    rows = []
    planted = [h for h in HOTSPOTS if h[0] in pop]
    for hd, hissue, count in planted:  # recent clusters the area analysis should find
        for _ in range(count):
            rows.append(make(ISSUE_DEPT[hissue], hissue, ISSUE_DAYS[hissue], hd, rng.uniform(0.2, 26)))
    for _ in range(n - len(rows)):
        dept_id = rng.choices(dept_ids, [DEPT_WEIGHT[d] for d in dept_ids])[0]
        issue, _w, mean_days = rng.choices(ISSUES[dept_id], [i[1] for i in ISSUES[dept_id]])[0]
        district = rng.choices(list(weights), list(weights.values()))[0]
        rows.append(make(dept_id, issue, mean_days, district, rng.betavariate(1.3, 1.0) * days))  # a little more volume recently
    df = pd.DataFrame(rows).sort_values("created_at", ignore_index=True)
    df.insert(0, "complaint_id", [f"DEMO-{i + 1:04d}" for i in range(len(df))])
    df["is_demo"] = True
    return df


def from_registry(conn, n: int = 360, seed: int = 2026) -> pd.DataFrame:
    """Demo tickets built on the registry's real districts (needs the registry to have been built)."""
    from dashboard.cm import registry as R

    districts = R.rows(conn, "SELECT name, division, population_2011 FROM districts")
    names = {r["id"]: r["name_en"] for r in R.rows(conn, "SELECT id, name_en FROM departments")}
    return generate(districts, names, n=n, seed=seed)


def main() -> None:
    from dashboard.cm import registry as R

    df = from_registry(R.connect())
    out = R.DATA_DIR / "demo_tickets.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"{len(df)} DEMO tickets -> {out}")


if __name__ == "__main__":
    main()
