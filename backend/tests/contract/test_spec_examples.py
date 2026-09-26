"""Every JSON example in API_SPEC.md must validate against the api.py models."""

import json
import re
from pathlib import Path

import pytest
from api import ErrorResponse, HealthResponse, MessageResponse, StatusResponse

SPEC = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "API_SPEC.md"
BLOCKS = re.findall(r"```json\r?\n(.*?)```", SPEC.read_text(encoding="utf-8"), re.DOTALL)


def model_for(payload: dict):
    if "error_code" in payload:
        return ErrorResponse
    if "action" in payload:
        return MessageResponse
    if "updated_at" in payload:
        return StatusResponse
    return HealthResponse


def test_spec_has_examples_for_every_model():
    models = {model_for(json.loads(block)) for block in BLOCKS}
    assert models == {ErrorResponse, MessageResponse, StatusResponse, HealthResponse}


@pytest.mark.parametrize("block", BLOCKS, ids=[f"example-{i}" for i in range(len(BLOCKS))])
def test_example_validates(block):
    payload = json.loads(block)
    model_for(payload).model_validate(payload)
