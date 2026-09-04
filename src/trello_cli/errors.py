from __future__ import annotations

from typing import Any


class TrelloCliError(Exception):
    """Base error. Carries a stable `code` for the JSON error contract."""

    code: str = "error"

    def __init__(self, message: str, *, details: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            out["details"] = self.details
        return out


class ConfigError(TrelloCliError):
    """Credentials missing or unreadable — the fix is environmental."""

    code = "config_error"


class ResolutionError(TrelloCliError):
    """A name (board / list / label / member / field) did not resolve to exactly one id."""

    code = "resolution_error"


class TrelloApiError(TrelloCliError):
    code = "trello_api_error"

    def __init__(self, message: str, *, status: int, details: object | None = None) -> None:
        super().__init__(message, details=details)
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out["status"] = self.status
        return out


class InputError(TrelloCliError):
    """Bad arguments — the caller can fix this without touching the environment."""

    code = "input_error"
