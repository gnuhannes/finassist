"""Domain exceptions raised by the services layer (review finding C5 / issue #107).

Services raise these instead of ``fastapi.HTTPException`` or bare ``ValueError``.
Routes let them propagate; the single handler registered in
``main.create_app`` turns ``status_code`` into the HTTP response. This removes
the per-route ``raise HTTPException(...)`` translation and the
``if "not found" in str(e)`` message-substring branching in ``routes/imports.py``.
"""

from __future__ import annotations


class ServiceError(Exception):
    """Base class for expected, client-facing service errors.

    ``status_code`` / ``default_detail`` are class attributes so subclasses just
    override them. ``detail`` is what the handler puts in the JSON body.
    """

    status_code = 400
    default_detail = "Request could not be processed"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class NotFoundError(ServiceError):
    status_code = 404
    default_detail = "Resource not found"


class ValidationError(ServiceError):
    status_code = 422
    default_detail = "Invalid input"


class ConflictError(ServiceError):
    status_code = 409
    default_detail = "Conflicting state"


class CsvFormatError(ServiceError):
    """The uploaded CSV can't be parsed at all (bad header, encoding, row cap).

    400 rather than 422: the file — not the request shape — is malformed, and
    this preserves the status code the import endpoint returned before #107.
    """

    status_code = 400
    default_detail = "CSV file could not be parsed"
