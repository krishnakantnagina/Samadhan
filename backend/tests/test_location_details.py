import pytest

from app import location_details as L


def test_registry_has_all_55_districts_with_unique_names():
    ds = L.load_districts()
    assert len(ds) == 55 and len({d.name_en for d in ds}) == 55 and len({d.code for d in ds}) == 55
    assert {d.division for d in ds} == {"Bhopal", "Chambal", "Gwalior", "Indore", "Jabalpur", "Narmadapuram", "Rewa", "Sagar", "Shahdol", "Ujjain"}


@pytest.mark.parametrize("said, english", [
    ("शाजापुर", "Shajapur"), ("इंदौर", "Indore"), ("इन्दौर", "Indore"), ("भिंड", "Bhind"), ("भिण्ड", "Bhind"), ("खंडवा", "Khandwa"), ("मंदसौर", "Mandsaur"),
    ("छिंदवाड़ा", "Chhindwara"), ("सीहोर", "Sehore"), ("सिहोर", "Sehore"), ("होशंगाबाद", "Narmadapuram"), ("आगर मालवा", "Agar Malwa"), ("अशोकनगर", "Ashoknagar"),
    ("Shajapura", "Shajapur"), ("rewa", "Rewa"), ("टीकमगढ़", "Tikamgarh"), ("सिंगरोली", "Singrauli"), ("पांढुर्ना", "Pandhurna"), ("अलीराजपुर", "Aalirajpur"),
])
def test_spelling_variants_match_the_official_district(said, english):
    assert L.match_district(said).name_en == english


def test_unrelated_text_matches_no_district():
    assert L.match_district("पानी नहीं आ रहा") is None and L.match_district("") is None


def test_answer_with_district_and_tehsil_markers():
    d = L.parse("शाजापुर जिला, कालापीपल तहसील")
    assert (d.district, d.district_hi, d.division, d.tehsil, d.nearest_place, d.unknown) == ("Shajapur", "शाजापुर", "Ujjain", "कालापीपल", None, False)
    d = L.parse("जिला रीवा")
    assert (d.district, d.tehsil) == ("Rewa", None)
    d = L.parse("Sagar district, Rehli tehsil")
    assert (d.district, d.tehsil) == ("Sagar", "Rehli")


def test_a_bare_district_and_a_nearest_place():
    assert L.parse("रीवा").district == "Rewa"
    d = L.parse("रामपुर के पास")
    assert (d.district, d.nearest_place) == (None, "रामपुर")
    d = L.parse("Rewa, near Mauganj chowk")
    assert d.district == "Rewa" and d.nearest_place.startswith("Mauganj")


def test_everyday_words_that_are_district_names_need_a_marker_or_a_very_short_answer():
    assert L.parse("सीधी जिला").district == "Sidhi"  # marker
    assert L.parse("सागर").district == "Sagar"  # the whole answer is one word
    long_answer = L.parse("मेरा घर सीधी सड़क के किनारे है और धार जैसी नहर है")
    assert long_answer.district is None  # "straight road" and "stream" are not districts


@pytest.mark.parametrize("said", ["पता नहीं", "मुझे नहीं पता", "I don't know", "pata nahi", "मालूम नहीं"])
def test_i_dont_know_is_a_valid_answer_and_is_kept_as_unknown(said):
    d = L.parse(said)
    assert d.unknown is True and not d.any and d.as_meta() == {"raw": said, "unknown": True}


def test_dont_know_with_something_useful_keeps_the_useful_part():
    d = L.parse("जिला नहीं पता, रामपुर के पास")
    assert d.nearest_place == "रामपुर" and d.unknown is False


def test_unclassifiable_answers_are_kept_for_the_officer_not_dropped():
    d = L.parse("बड़े मंदिर वाली गली")
    assert d.district is None and d.nearest_place == "बड़े मंदिर वाली गली" and d.any
    assert L.parse("").any is False


def test_as_meta_is_json_friendly_and_omits_empty_values():
    meta = L.parse("शाजापुर जिला, कालापीपल तहसील").as_meta()
    assert meta["district"] == "Shajapur" and meta["tehsil"] == "कालापीपल" and "nearest_place" not in meta and "unknown" not in meta


def test_tehsil_after_a_connector_is_the_name_not_the_connector():
    # real voice answer from 2026-10-07 (ticket SMD-0024): the tehsil was saved as "पर" ("but")
    got = L.parse("सबसे कने तो सारंगपुर है पर तहसील गुलाना है।")
    assert got.tehsil == "गुलाना"
    assert got.nearest_place == "सारंगपुर"  # कने = Bundeli "near"; Sarangpur is a town, not one of the 55 districts
    assert got.district is None


@pytest.mark.parametrize(
    ("text", "tehsil", "nearest"),
    [
        ("गुलाना तहसील, राजगढ़ जिला", "गुलाना", None),
        ("तहसील गुलाना", "गुलाना", None),
        ("सबसे नजदीक कस्बा बैरसिया है", None, "बैरसिया"),
        ("रामपुर के पास", None, "रामपुर"),
    ],
)
def test_tehsil_and_nearest_place_forms(text, tehsil, nearest):
    got = L.parse(text)
    assert (got.tehsil, got.nearest_place) == (tehsil, nearest)
