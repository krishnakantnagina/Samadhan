"""S03 service spec loader: the real water_supply.yaml loads, and broken files fail loudly."""

import re
from pathlib import Path

import pytest

from app.service_spec import SpecError, load_spec, load_specs

SPECS_DIR = Path(__file__).resolve().parents[3] / "specs"
GOOD = (SPECS_DIR / "water_supply.yaml").read_text(encoding="utf-8")


def write(tmp_path: Path, text: str, name: str = "water_supply.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def expect_error(tmp_path: Path, text: str, *needles: str, name: str = "water_supply.yaml"):
    with pytest.raises(SpecError) as info:
        load_spec(write(tmp_path, text, name))
    message = str(info.value)
    assert name in message
    for needle in needles:
        assert needle in message, message


def replace_once(old: str, new: str) -> str:
    assert GOOD.count(old) == 1, old
    return GOOD.replace(old, new)


# --- The real file -----------------------------------------------------------------------


def test_water_supply_loads():
    spec = load_spec(SPECS_DIR / "water_supply.yaml")
    assert spec.service == "water_supply"
    assert spec.department == "Jal Vibhag"
    assert spec.pilot.wards == 5
    assert spec.routing.min_confidence == 0.7
    assert spec.routing.fallback_level == "district"
    assert spec.routing.fallback_status == "needs_review"


def test_required_fields_are_issue_and_location_only():
    """Scenario 1/2: the bot may only ever ask for these two."""
    spec = load_spec(SPECS_DIR / "water_supply.yaml")
    assert [f.name for f in spec.required_fields()] == ["issue_type", "location"]
    assert [f.name for f in spec.fields] == [
        "issue_type",
        "location",
        "duration_days",
        "address_detail",
    ]


def test_location_ask_for_matches_s01():
    spec = load_spec(SPECS_DIR / "water_supply.yaml")
    assert spec.field("location").ask_for == "location"


def test_every_required_field_has_a_question_in_both_languages():
    for field in load_spec(SPECS_DIR / "water_supply.yaml").required_fields():
        assert field.question.hi and field.question.en


def test_field_lookup():
    spec = load_spec(SPECS_DIR / "water_supply.yaml")
    assert spec.field("issue_type").type == "enum"
    assert spec.field("nope") is None


def test_load_specs_keys_by_service_id():
    specs = load_specs(SPECS_DIR)
    assert sorted(specs) == ["electricity", "human_evaluation", "roads", "sanitation", "water_supply"]  # S28


def test_load_specs_rejects_a_directory_without_specs(tmp_path):
    with pytest.raises(SpecError, match="no service specs"):
        load_specs(tmp_path)


# --- Broken files (each must name the file and the problem) ---------------------------------


def test_unknown_top_level_key(tmp_path):
    expect_error(tmp_path, replace_once("department:", "dept:"), "department", "dept")


def test_unknown_field_key(tmp_path):
    expect_error(
        tmp_path, replace_once("    max: 365\n", "    max: 365\n    colour: red\n"), "colour"
    )


def test_duplicate_key_is_rejected_not_overridden(tmp_path):
    text = replace_once("department: Jal Vibhag", "department: Jal Vibhag\ndepartment: Other")
    expect_error(tmp_path, text, "duplicate key", "department")


def test_duplicate_field_name(tmp_path):
    text = replace_once("  - name: address_detail", "  - name: duration_days")
    expect_error(tmp_path, text, "duplicate field name", "duration_days")


def test_required_field_without_question(tmp_path):
    block = re.search(r"    question:\n      hi: \"आपको.*\n      en: \".*\n", GOOD)
    assert block, "issue_type question block not found"
    expect_error(tmp_path, GOOD.replace(block.group(0), ""), "issue_type", "needs a question")


def test_no_required_field(tmp_path):
    text = GOOD.replace("required: true", "required: false")
    expect_error(tmp_path, text, "at least one field must be required")


def test_service_must_match_filename(tmp_path):
    expect_error(tmp_path, GOOD, "must equal the filename", name="sanitation.yaml")


def test_bad_fallback_level(tmp_path):
    expect_error(
        tmp_path, replace_once("fallback_level: district", "fallback_level: city"), "fallback_level"
    )


def test_bad_fallback_status(tmp_path):
    expect_error(
        tmp_path,
        replace_once("fallback_status: needs_review", "fallback_status: open"),
        "fallback_status",
    )


def test_confidence_out_of_range(tmp_path):
    expect_error(
        tmp_path, replace_once("min_confidence: 0.7", "min_confidence: 1.5"), "min_confidence"
    )


def test_enum_with_one_value(tmp_path):
    text = re.sub(r"(      - \{value: no_supply.*\n)(      - \{value.*\n)+", r"\1", GOOD)
    expect_error(tmp_path, text, "values")


def test_integer_min_greater_than_max(tmp_path):
    text = replace_once("    min: 0 ", "    min: 999 ")
    expect_error(tmp_path, text, "min must be <= max")


def test_unknown_field_type(tmp_path):
    expect_error(tmp_path, replace_once("type: integer", "type: float"), "type")


def test_unquoted_colon_is_a_clear_yaml_error(tmp_path):
    text = replace_once(
        'en: "What is the water problem: no water, low pressure, dirty water or a leak?"',
        "en: What is the water problem: no water, low pressure, dirty water or a leak?",
    )
    expect_error(tmp_path, text, "invalid YAML")


def test_top_level_must_be_a_mapping(tmp_path):
    expect_error(tmp_path, "- just\n- a list\n", "mapping")


def test_missing_file(tmp_path):
    with pytest.raises(SpecError, match="cannot read"):
        load_spec(tmp_path / "missing.yaml")
