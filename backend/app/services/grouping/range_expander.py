import re
from typing import NamedTuple, Optional


class RangeExpansionResult(NamedTuple):
    raw_text: str
    expanded_numbers: list[str]
    is_ambiguous: bool
    error_message: Optional[str]


class InvoiceRangeExpander:
    """Conservatively expands handwritten and printed invoice reference strings into discrete numbers.

    Supported patterns:
    - Suffix range: '2250601397 to 1400' -> ['2250601397', '2250601398', '2250601399', '2250601400']
    - Short suffix range: '2250501854 to 56' -> ['2250501854', '2250501855', '2250501856']
    - Slash range: '1250510479/480' -> ['1250510479', '1250510480']
    - Delimited lists: '2250501852, 2250501853' -> ['2250501852', '2250501853']

    Safety:
    - Never invent numbers when ambiguous, descending, or exceeding max span limit (50).
    - Preserves original raw text.
    """

    MAX_SAFE_SPAN = 50

    @classmethod
    def expand(cls, raw_text: Optional[str]) -> RangeExpansionResult:
        if not raw_text or not raw_text.strip():
            return RangeExpansionResult(
                raw_text="" if raw_text is None else raw_text,
                expanded_numbers=[],
                is_ambiguous=False,
                error_message=None,
            )

        cleaned = raw_text.strip()
        # Remove common prefixes like 'Inv:', 'Invoices:', 'Inv nos:'
        content = re.sub(r"^(?:inv(?:oices?)?[:\s]*|inv(?:oice)?\s*nos?\.?[:\s]*)", "", cleaned, flags=re.IGNORECASE).strip()

        # Check for range syntax: 'START to END' or 'START - END' or 'START / END'
        range_match = re.search(r"^(\d+)\s*(?:to|-|–|/)\s*(\d+)$", content, re.IGNORECASE)
        if range_match:
            start_str = range_match.group(1)
            end_str = range_match.group(2)

            # Determine prefix alignment
            if len(start_str) > len(end_str):
                # Suffix replacement: e.g. 2250601397 to 1400 or 2250501854 to 56
                suffix_len = len(end_str)
                prefix = start_str[:-suffix_len]
                start_suffix_val = int(start_str[-suffix_len:])
                end_suffix_val = int(end_str)

                # Guard against descending or illogical range
                if end_suffix_val < start_suffix_val:
                    return RangeExpansionResult(
                        raw_text=cleaned,
                        expanded_numbers=[],
                        is_ambiguous=True,
                        error_message=f"Descending invoice range detected: '{start_str}' to '{end_str}'",
                    )

                span = end_suffix_val - start_suffix_val + 1
                if span > cls.MAX_SAFE_SPAN:
                    return RangeExpansionResult(
                        raw_text=cleaned,
                        expanded_numbers=[],
                        is_ambiguous=True,
                        error_message=f"Invoice range span ({span}) exceeds maximum safe limit ({cls.MAX_SAFE_SPAN})",
                    )

                expanded = [f"{prefix}{val:0{suffix_len}d}" for val in range(start_suffix_val, end_suffix_val + 1)]
                return RangeExpansionResult(
                    raw_text=cleaned,
                    expanded_numbers=expanded,
                    is_ambiguous=False,
                    error_message=None,
                )

            elif len(start_str) == len(end_str):
                # Both full numbers: e.g. 1001 to 1004
                start_val = int(start_str)
                end_val = int(end_str)

                if end_val < start_val:
                    return RangeExpansionResult(
                        raw_text=cleaned,
                        expanded_numbers=[],
                        is_ambiguous=True,
                        error_message=f"Descending invoice range detected: '{start_str}' to '{end_str}'",
                    )

                span = end_val - start_val + 1
                if span > cls.MAX_SAFE_SPAN:
                    return RangeExpansionResult(
                        raw_text=cleaned,
                        expanded_numbers=[],
                        is_ambiguous=True,
                        error_message=f"Invoice range span ({span}) exceeds maximum safe limit ({cls.MAX_SAFE_SPAN})",
                    )

                pad_len = len(start_str)
                expanded = [f"{val:0{pad_len}d}" for val in range(start_val, end_val + 1)]
                return RangeExpansionResult(
                    raw_text=cleaned,
                    expanded_numbers=expanded,
                    is_ambiguous=False,
                    error_message=None,
                )
            else:
                # end_str has more digits than start_str -> ambiguous / malformed
                return RangeExpansionResult(
                    raw_text=cleaned,
                    expanded_numbers=[],
                    is_ambiguous=True,
                    error_message=f"Malformed invoice range: end '{end_str}' longer than start '{start_str}'",
                )

        # Check for discrete list of numbers (separated by comma, semicolon, space, or slash)
        # e.g. "2250501852, 2250501853" or "2250501852"
        tokens = re.split(r"[\s,;]+", content)
        all_digits = [t for t in tokens if t.isdigit()]

        # If there are non-digit tokens that look like text instructions, mark as ambiguous
        non_digits = [t for t in tokens if t and not t.isdigit() and t.lower() not in {"and", "&"}]
        if non_digits:
            return RangeExpansionResult(
                raw_text=cleaned,
                expanded_numbers=all_digits,
                is_ambiguous=True,
                error_message=f"Unrecognized non-numeric tokens in invoice list: {non_digits}",
            )

        if all_digits:
            return RangeExpansionResult(
                raw_text=cleaned,
                expanded_numbers=all_digits,
                is_ambiguous=False,
                error_message=None,
            )

        return RangeExpansionResult(
            raw_text=cleaned,
            expanded_numbers=[],
            is_ambiguous=True,
            error_message="Could not parse any valid invoice numbers from reference string",
        )
