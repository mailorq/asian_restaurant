"""
the whole path a staff role travels: storefront payload -> bridge -> contract -> projection

the bridge rebuilds this event field by field, so a field it does not name is silently dropped
that is invisible to both sides: Operations keeps authorizing by the old boolean and looks healthy
"""

import pytest
from event_contracts import EVENT_AUTHZ_CHANGED, parse_event

from operations import projection
from operations.management.commands.bridge_storefront_events import _map_data, build_envelope
from operations.models import EmployeeAuthorization

pytestmark = pytest.mark.django_db

OPERATOR = "restaurant_operator"
SUBJECT = 77
OCCURRED_AT = "2026-01-01T00:00:00+00:00"


class _Properties:
    def __init__(self, version):
        self.headers = {"event_id": "11111111-1111-1111-1111-111111111111",
                        "correlation_id": "22222222-2222-2222-2222-222222222222",
                        "aggregate_version": version, "occurred_at": OCCURRED_AT}
        self.message_id = "m-1"
        self.correlation_id = None
        self.type = "identity.authz_changed"


def _legacy(roles, version=5, role_active=True, user_active=True):
    payload = {"subject_id": SUBJECT, "authz_version": version,
               "role_active": role_active, "user_active": user_active}
    if roles is not None:
        payload["roles"] = roles
    return payload


def _deliver(roles, version=5, **kw):
    legacy = _legacy(roles, version=version, **kw)
    envelope = build_envelope(_Properties(version), EVENT_AUTHZ_CHANGED, legacy)
    parsed, data = parse_event(envelope)
    projection.dispatch_authz(parsed, data) if hasattr(projection, "dispatch_authz") else \
        projection._authz_changed(parsed, data)
    return EmployeeAuthorization.objects.get(subject_id=SUBJECT)


def test_a_role_survives_the_bridge():
    assert _map_data(EVENT_AUTHZ_CHANGED, _legacy([OPERATOR]))["roles"] == [OPERATOR]


def test_a_payload_without_roles_carries_none_rather_than_an_empty_list():
    assert "roles" not in _map_data(EVENT_AUTHZ_CHANGED, _legacy(None))


def test_the_role_reaches_the_projection():
    assert _deliver([OPERATOR]).roles == [OPERATOR]


def test_the_projection_records_that_roles_are_known():
    assert _deliver([OPERATOR]).roles_known is True


def test_a_payload_predating_roles_leaves_them_unknown():
    row = _deliver(None)

    assert row.roles == [] and row.roles_known is False


def test_a_backfill_at_the_same_version_fills_the_roles_in():
    """the version does not move on a backfill, so this must not read as a conflict"""
    _deliver(None, version=5)

    row = _deliver([OPERATOR], version=5)

    assert row.roles == [OPERATOR] and row.roles_known is True


def test_a_contradiction_at_the_same_version_is_still_a_conflict():
    _deliver([OPERATOR], version=5)

    with pytest.raises(projection.ProjectionConflict):
        _deliver([OPERATOR], version=5, user_active=False)


def test_known_roles_are_never_downgraded_to_unknown_at_the_same_version():
    _deliver([OPERATOR], version=5)

    row = _deliver(None, version=5)

    assert row.roles == [OPERATOR] and row.roles_known is True


def test_a_newer_event_without_roles_forgets_the_ones_it_replaces():
    """a mixed state would pair a new boolean with a role nobody re-confirmed"""
    _deliver([OPERATOR], version=5)

    row = _deliver(None, version=6)

    assert row.roles == [] and row.roles_known is False
    assert row.authz_version == 6


def test_the_contract_refuses_a_payload_whose_flag_and_roles_disagree():
    from event_contracts.events import AuthzChangedData
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AuthzChangedData(subject_id=1, authz_version=1, role_active=False,
                         roles=[OPERATOR], user_active=True)
    with pytest.raises(ValidationError):
        AuthzChangedData(subject_id=1, authz_version=1, role_active=True,
                         roles=[], user_active=True)


def test_a_payload_without_roles_may_still_say_anything_about_the_flag():
    from event_contracts.events import AuthzChangedData

    assert AuthzChangedData(subject_id=1, authz_version=1, role_active=True,
                            user_active=True).role_active is True
