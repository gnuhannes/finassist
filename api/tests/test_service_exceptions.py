"""Service exception hierarchy + central HTTP mapping (issue #107 / C5).

End-to-end mapping is covered by the endpoint tests (a bad ``month`` -> 422 in
``test_reports_monthly``, a missing account -> 404 in ``test_import_endpoint``,
cold-start -> 400 in ``test_ml_routes``). This file pins the contract those
rely on.
"""

from __future__ import annotations

import pytest

from my_private_finances.services.exceptions import (
    ConflictError,
    CsvFormatError,
    NotFoundError,
    ServiceError,
    ValidationError,
)
from my_private_finances.services.ml_categorization import ColdStartError
from my_private_finances.services.reporting import AccountNotFound, InvalidMonth


@pytest.mark.parametrize(
    ("exc", "status_code"),
    [
        (ServiceError(), 400),
        (NotFoundError(), 404),
        (ValidationError(), 422),
        (ConflictError(), 409),
        (CsvFormatError(), 400),
        (ColdStartError(), 400),
        (AccountNotFound(), 404),
        (InvalidMonth(), 422),
    ],
)
def test_status_codes(exc: ServiceError, status_code: int) -> None:
    assert exc.status_code == status_code
    assert isinstance(exc, ServiceError)


def test_detail_defaults_and_override() -> None:
    assert NotFoundError().detail == NotFoundError.default_detail
    assert NotFoundError("Account 7 not found").detail == "Account 7 not found"
    assert str(NotFoundError("boom")) == "boom"


def test_reporting_errors_extend_the_shared_hierarchy() -> None:
    assert issubclass(InvalidMonth, ValidationError)
    assert issubclass(AccountNotFound, NotFoundError)
