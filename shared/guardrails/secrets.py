"""Deterministic runtime secret detection and non-reversible redaction."""

from __future__ import annotations

import logging
import math
import re
import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from .config import Settings
from .models import DetectedEntity, RedactionResult
from .redactor import redact_text

logger = logging.getLogger(__name__)

_SOURCE = "deterministic-secret-detector"
_SAFE_KEYWORD = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_VALUE_CHARACTERS = r"A-Za-z0-9_./+~=-"


@dataclass(frozen=True, slots=True)
class SecretRule:
    """A compiled structural signature and the group containing the secret."""

    category: str
    pattern: re.Pattern[str]
    confidence: float
    value_group: str = "value"


_STRUCTURAL_RULES = (
    SecretRule(
        "PrivateKey",
        re.compile(
            r"(?P<value>-----BEGIN (?P<label>(?:RSA |EC |OPENSSH )?PRIVATE KEY)-----"
            r"[\s\S]+?-----END (?P=label)-----)"
        ),
        1.0,
    ),
    SecretRule(
        "GitHubToken",
        re.compile(
            r"(?<![A-Za-z0-9_])(?P<value>(?:gh[pousr]_[A-Za-z0-9]{20,}"
            r"|github_pat_[A-Za-z0-9_]{20,}))(?![A-Za-z0-9_])"
        ),
        1.0,
    ),
    SecretRule(
        "ProviderApiKey",
        re.compile(
            r"(?<![A-Za-z0-9_-])(?P<value>sk-(?:proj-)?[A-Za-z0-9_-]{20,})"
            r"(?![A-Za-z0-9_-])"
        ),
        1.0,
    ),
    SecretRule(
        "JsonWebToken",
        re.compile(
            r"(?<![A-Za-z0-9_-])(?P<value>eyJ[A-Za-z0-9_-]{8,}"
            r"\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})(?![A-Za-z0-9_-])"
        ),
        0.99,
    ),
    SecretRule(
        "BearerToken",
        re.compile(
            rf"(?i:\bBearer\s+)(?P<value>[{_VALUE_CHARACTERS}]{{16,}})"
        ),
        0.98,
    ),
    SecretRule(
        "SasSignature",
        re.compile(r"(?i:[?&]sig=)(?P<value>[^&\s\"']{8,})"),
        0.98,
    ),
    SecretRule(
        "ConnectionStringSecret",
        re.compile(
            r"(?i:\b(?:AccountKey|SharedAccessKey|SharedAccessSignature|"
            r"Password|Pwd)\s*=\s*)[\"']?(?P<value>[^;\s\"']{8,})"
        ),
        0.97,
    ),
)

_DEFAULT_KEYWORDS = (
    "access_token",
    "api_key",
    "apikey",
    "client_secret",
    "password",
    "refresh_token",
    "secret",
    "token",
)


def _shannon_entropy(value: str) -> float:
    counts = Counter(value)
    length = len(value)
    return -sum(
        (count / length) * math.log2(count / length) for count in counts.values()
    )


def _generic_pattern(keywords: Iterable[str]) -> re.Pattern[str]:
    unique = sorted(set(keywords), key=len, reverse=True)
    invalid = [keyword for keyword in unique if not _SAFE_KEYWORD.fullmatch(keyword)]
    if invalid:
        raise ValueError("Secret keywords must contain only safe identifier characters")
    names = "|".join(re.escape(keyword) for keyword in unique)
    return re.compile(
        rf"(?i:\b(?:{names})\b[\"']?\s*[:=]\s*)"
        rf"[\"']?(?P<value>[{_VALUE_CHARACTERS}]{{12,}})"
    )


class SecretDetector:
    """Detect runtime credentials locally without validating or transmitting them."""

    def __init__(
        self,
        *,
        minimum_entropy: float = 3.0,
        additional_keywords: Iterable[str] = (),
    ) -> None:
        self.minimum_entropy = minimum_entropy
        self._generic = SecretRule(
            "GenericSecret",
            _generic_pattern((*_DEFAULT_KEYWORDS, *additional_keywords)),
            0.85,
        )

    def detect(self, text: str) -> list[DetectedEntity]:
        detections: list[DetectedEntity] = []
        for rule in (*_STRUCTURAL_RULES, self._generic):
            for match in rule.pattern.finditer(text):
                value = match.group(rule.value_group)
                if rule.category == "GenericSecret" and (
                    _shannon_entropy(value) < self.minimum_entropy
                ):
                    continue
                detections.append(
                    DetectedEntity(
                        category=rule.category,
                        offset=match.start(rule.value_group),
                        length=len(value),
                        confidence=rule.confidence,
                        source=_SOURCE,
                        value=value,
                    )
                )
        return detections


class SecretRedactionService:
    """Coordinate local secret detection and deterministic replacement."""

    def __init__(
        self,
        settings: Settings | None = None,
        detector: SecretDetector | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.detector = detector or SecretDetector(
            minimum_entropy=self.settings.secret_minimum_entropy,
            additional_keywords=self.settings.secret_additional_keywords,
        )

    def redact(
        self,
        text: str,
        *,
        correlation_id: str | None = None,
    ) -> RedactionResult:
        request_id = correlation_id or str(uuid.uuid4())
        result = redact_text(
            text,
            self.detector.detect(text),
            threshold=0.0,
            correlation_id=request_id,
        )
        logger.info(
            "Secret redaction completed correlation_id=%s detection_count=%d categories=%s",
            request_id,
            len(result.entities),
            sorted(result.entity_counts),
        )
        return result
