import re
from typing import Optional
from backend.app.schemas.extraction import LRNumberField


class LRNormalizer:
    """Utilities for parsing, normalizing, and comparing LR numbers."""

    @staticmethod
    def normalize(
        raw_text: str,
        source_page: int,
        confidence: float = 1.0,
        bounding_box: Optional[list[list[float]]] = None,
    ) -> LRNumberField:
        """Parses raw LR string and creates a structured LRNumberField.

        Preserves original raw text while stripping leading zeros for normalization,
        per PRD §4 (e.g. '019427' -> '19427').
        """
        cleaned_raw = raw_text.strip()
        # Extract alphanumeric core (usually digits for CTLS LRs)
        digits_match = re.search(r"\d+", cleaned_raw)
        if digits_match:
            digits = digits_match.group(0)
            normalized = digits.lstrip("0") or "0"
            is_ambiguous = len(digits) < 4
            flag_reason = (
                "Suspiciously short LR number" if is_ambiguous else None
            )
        else:
            normalized = cleaned_raw.lstrip("0") or cleaned_raw
            is_ambiguous = True
            flag_reason = "Non-standard LR number format"

        return LRNumberField(
            raw_value=cleaned_raw,
            normalized_value=normalized,
            confidence=confidence,
            bounding_box=bounding_box,
            source_page=source_page,
            is_ambiguous=is_ambiguous,
            flag_reason=flag_reason,
        )

    @staticmethod
    def match(lr_a: LRNumberField, lr_b: LRNumberField) -> bool:
        """Compares two LR numbers using normalized values.

        Returns True if their normalized values match, ignoring leading zeros.
        """
        return lr_a.normalized_value == lr_b.normalized_value
