import re
from typing import Optional
from backend.app.schemas.classification import (
    PageClassificationResult,
    PageClassificationType,
)


class TirunelveliPageClassifier:
    """Classifies Tirunelveli logistics pages based on structural text anchors and patterns.

    Recognizes:
    - MATERIAL_INVOICE (Seshasayee Paper 'Tax Invoice - Transport Copy')
    - EWAY_BILL (Government e-Way Bill printout)
    - SECURITY_COPY (Gate sheet listing all invoices and totals)
    - LORRY_RECEIPT (CTLS Consignment Note)
    - UNKNOWN_PAGE (When signals are ambiguous, low-confidence, or contradictory)
    """

    # Primary anchors with positive weights
    INVOICE_ANCHORS = [
        (r"tax invoice\s*[-–]?\s*transport copy", 5.0),
        (r"tax invoice", 2.0),
        (r"seshasayee paper and boards", 3.0),
        (r"net claim rs", 4.0),
        (r"add:\s*frie?ght", 4.0),
        (r"transport copy", 3.0),
        (r"bill to", 1.5),
        (r"ship to", 1.5),
        (r"gross wt|gross weight", 2.0),
    ]

    EWAY_ANCHORS = [
        (r"e-?way bill system", 5.0),
        (r"e-?way bill", 3.0),
        (r"valid upto|valid until|valid from", 4.0),
        (r"transporter doc\.?\s*no", 4.0),
        (r"government of india", 3.0),
        (r"\b\d{12}\b", 3.0),  # 12-digit e-way bill number
    ]

    SECURITY_ANCHORS = [
        (r"security copy", 6.0),
        (r"gate sheet", 4.0),
        (r"seshasayee paper.*security copy", 6.0),
        (r"lorry\s*no\s*:", 3.0),
        (r"transporter name\s*:\s*ct logistics", 4.0),
    ]

    LR_ANCHORS = [
        (r"ct logistics solutions", 4.0),
        (r"lorry receipt|consignment note", 4.0),
        (r"to be billed\s*/?\s*unloading by consignee", 5.0),
        (r"consignor['’]?s? name", 3.0),
        (r"consignee['’]?s? name", 3.0),
        (r"truck number|vehicle number", 1.5),
        (r"delivery at\s*/?\s*to", 2.5),
        (r"description of goods", 2.0),
    ]

    @classmethod
    def classify_page(
        cls,
        text: Optional[str],
        page_number: int,
    ) -> PageClassificationResult:
        """Classifies a page's text into one of the Tirunelveli page types."""
        if not text or not text.strip():
            return PageClassificationResult(
                page_number=page_number,
                classification=PageClassificationType.UNKNOWN_PAGE,
                confidence=0.0,
                detected_anchors=[],
                is_ambiguous=True,
                review_reason="Page has no extracted text or is completely blank",
            )

        cleaned_text = text.lower()

        scores: dict[PageClassificationType, float] = {
            PageClassificationType.MATERIAL_INVOICE: 0.0,
            PageClassificationType.EWAY_BILL: 0.0,
            PageClassificationType.SECURITY_COPY: 0.0,
            PageClassificationType.LORRY_RECEIPT: 0.0,
        }
        detected_anchors: dict[PageClassificationType, list[str]] = {
            t: [] for t in scores
        }

        # Match Material Invoice anchors
        for pattern, weight in cls.INVOICE_ANCHORS:
            if re.search(pattern, cleaned_text):
                scores[PageClassificationType.MATERIAL_INVOICE] += weight
                detected_anchors[PageClassificationType.MATERIAL_INVOICE].append(pattern)

        # Match E-way Bill anchors
        for pattern, weight in cls.EWAY_ANCHORS:
            if re.search(pattern, cleaned_text):
                scores[PageClassificationType.EWAY_BILL] += weight
                detected_anchors[PageClassificationType.EWAY_BILL].append(pattern)

        # Match Security Copy anchors
        for pattern, weight in cls.SECURITY_ANCHORS:
            if re.search(pattern, cleaned_text):
                scores[PageClassificationType.SECURITY_COPY] += weight
                detected_anchors[PageClassificationType.SECURITY_COPY].append(pattern)

        # Match LR anchors
        for pattern, weight in cls.LR_ANCHORS:
            if re.search(pattern, cleaned_text):
                scores[PageClassificationType.LORRY_RECEIPT] += weight
                detected_anchors[PageClassificationType.LORRY_RECEIPT].append(pattern)

        # Rank types by score
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_type, top_score = ranked[0]
        runner_up_type, runner_up_score = ranked[1]

        # Minimum score threshold to qualify as known document
        CONFIDENCE_THRESHOLD = 4.0

        if top_score < CONFIDENCE_THRESHOLD:
            return PageClassificationResult(
                page_number=page_number,
                classification=PageClassificationType.UNKNOWN_PAGE,
                confidence=round(min(top_score / 10.0, 0.49), 2),
                detected_anchors=detected_anchors[top_type],
                is_ambiguous=True,
                review_reason=(
                    f"Insufficient distinctive markers (top score: {top_score:.1f} on {top_type.value}). "
                    "Flagged for manual page classification."
                ),
            )

        # Check for ambiguity (runner up too close to top score)
        is_ambiguous = (top_score - runner_up_score) < 2.0 and runner_up_score > 3.0
        review_reason = (
            f"Conflicting document markers between {top_type.value} and {runner_up_type.value}"
            if is_ambiguous
            else None
        )

        confidence = round(min(0.5 + (top_score / 15.0) * 0.5, 0.99), 2)

        return PageClassificationResult(
            page_number=page_number,
            classification=top_type,
            confidence=confidence,
            detected_anchors=detected_anchors[top_type],
            is_ambiguous=is_ambiguous,
            review_reason=review_reason,
        )
