"""GET /api/v1/status/{complaint_id} — S01 section 5 (scenarios 8 and 9)."""

import os

import pytest
from app.schemas import ComplaintStatus, ErrorCode, StatusResponse
from contract_helpers import assert_error, post_message

EXISTING_ID = os.environ.get("CONTRACT_EXISTING_ID", "SMD-0042")
ALLOWED_FIELDS = {"complaint_id", "status", "department", "updated_at"}


def get_status(client, complaint_id):
    return client.get(f"/api/v1/status/{complaint_id}")


def test_existing_id_returns_only_the_four_allowed_fields(client):
    response = get_status(client, EXISTING_ID)
    assert response.status_code == 200, response.text
    assert set(response.json()) == ALLOWED_FIELDS
    body = StatusResponse.model_validate(response.json())
    assert body.complaint_id == EXISTING_ID
    assert body.department.strip()


@pytest.mark.mock_only
def test_scenario_9_officer_status_is_visible(client):
    body = StatusResponse.model_validate(get_status(client, "SMD-0042").json())
    assert body.status == ComplaintStatus.IN_PROGRESS


@pytest.mark.mock_only
def test_scenario_8_district_ticket_status_is_needs_review(client):
    created = post_message(client, text="mock:submitted_district").json()["ticket"]["complaint_id"]
    body = StatusResponse.model_validate(get_status(client, created).json())
    assert body.status == ComplaintStatus.NEEDS_REVIEW


@pytest.mark.mock_only
def test_ticket_created_by_message_can_be_looked_up(client):
    created = post_message(client, text="mock:submitted").json()["ticket"]
    body = StatusResponse.model_validate(get_status(client, created["complaint_id"]).json())
    assert body.status == ComplaintStatus(created["status"])
    assert body.department == created["department"]


@pytest.mark.parametrize(
    "complaint_id", ["SMD-ABC", "SMD-1", "SMD-123", "smd-0042", "SMD0042", "0042", "SMD-004a"]
)
def test_malformed_id_is_400(client, complaint_id):
    assert_error(get_status(client, complaint_id), 400, ErrorCode.INVALID_COMPLAINT_ID)


def test_unknown_id_is_404(client):
    assert_error(get_status(client, "SMD-9999999"), 404, ErrorCode.COMPLAINT_NOT_FOUND)
