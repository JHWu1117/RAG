"""Deterministic privacy screening for offline training inputs.

The filter never returns a detected secret or PII value. Findings contain a
kind, JSON-style path, and one-way fingerprint so quarantine records remain
auditable without becoming another copy of the sensitive input.
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class FindingKind(str, Enum):
    API_SECRET = "api_secret"
    EMAIL = "email"
    PHONE = "phone"


@dataclass(frozen=True)
class PrivacyFinding:
    """A sensitive-value occurrence with no recoverable raw value."""

    kind: FindingKind
    path: str
    fingerprint: str


@dataclass(frozen=True)
class PrivacyResult:
    """A deep-copied, redacted value and its findings."""

    value: Any
    findings: tuple[PrivacyFinding, ...]

    @property
    def is_safe(self) -> bool:
        return not self.findings


class PrivacyFilter:
    """Find API credentials, email addresses, and Chinese mobile numbers."""

    REDACTED = "[REDACTED]"
    _SENSITIVE_KEYS = frozenset(
        {
            "api_key",
            "apikey",
            "access_key",
            "access_token",
            "authorization",
            "bearer_token",
            "password",
            "secret",
            "token",
        }
    )
    _PATTERNS = (
        (
            FindingKind.API_SECRET,
            re.compile(r"(?<![\w-])sk-(?:ws-)?[A-Za-z0-9._-]{12,}"),
        ),
        (
            FindingKind.API_SECRET,
            re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}={0,2}"),
        ),
        (
            FindingKind.EMAIL,
            re.compile(r"(?i)(?<![\w.+-])[\w.+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])"),
        ),
        (
            FindingKind.PHONE,
            re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)"),
        ),
    )

    def screen(self, value: Any) -> PrivacyResult:
        """Return a redacted deep copy; never modify *value* in place."""

        findings: list[PrivacyFinding] = []
        redacted = self._walk(copy.deepcopy(value), "$", findings)
        return PrivacyResult(redacted, tuple(findings))

    def _walk(
        self,
        value: Any,
        path: str,
        findings: list[PrivacyFinding],
    ) -> Any:
        if isinstance(value, Mapping):
            output: dict[Any, Any] = {}
            for key, item in value.items():
                child_path = f"{path}.{key}"
                normalized_key = str(key).strip().lower().replace("-", "_")
                if normalized_key in self._SENSITIVE_KEYS and item not in (None, ""):
                    findings.append(
                        self._finding(FindingKind.API_SECRET, child_path, str(item))
                    )
                    output[key] = self.REDACTED
                else:
                    output[key] = self._walk(item, child_path, findings)
            return output
        if isinstance(value, list):
            return [
                self._walk(item, f"{path}[{index}]", findings)
                for index, item in enumerate(value)
            ]
        if isinstance(value, tuple):
            return tuple(
                self._walk(item, f"{path}[{index}]", findings)
                for index, item in enumerate(value)
            )
        if isinstance(value, str):
            return self._redact_text(value, path, findings)
        return copy.deepcopy(value)

    def _redact_text(
        self,
        text: str,
        path: str,
        findings: list[PrivacyFinding],
    ) -> str:
        redacted = text
        for kind, pattern in self._PATTERNS:

            def replace(
                match: re.Match[str], *, finding_kind: FindingKind = kind
            ) -> str:
                findings.append(self._finding(finding_kind, path, match.group(0)))
                return self.REDACTED

            redacted = pattern.sub(replace, redacted)
        return redacted

    @staticmethod
    def _finding(kind: FindingKind, path: str, raw_value: str) -> PrivacyFinding:
        digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()
        return PrivacyFinding(kind=kind, path=path, fingerprint=f"sha256:{digest}")


__all__ = [
    "FindingKind",
    "PrivacyFilter",
    "PrivacyFinding",
    "PrivacyResult",
]
