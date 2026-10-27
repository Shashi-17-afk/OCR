import re
from typing import Optional

from backend.app.schemas.document import OCRLineResult
from backend.app.schemas.extraction import EwayBillData, ExtractedField
from backend.app.services.extraction.tirunelveli.lr_normalizer import LRNormalizer


class EwayBillExtractor:
    """Extracts raw fields from Tirunelveli E-Way Bill printouts."""

    @classmethod
    def extract(
        cls,
        text: str,
        page_number: int,
        bounding_boxes: Optional[list[OCRLineResult]] = None,
    ) -> EwayBillData:
        def find_box(pattern: str) -> Optional[list[list[float]]]:
            if not bounding_boxes:
                return None
            for item in bounding_boxes:
                if re.search(pattern, item.text, re.IGNORECASE):
                    return item.box
            return None

        # 1. E-Way Bill Number (12 digits)
        ewb_match = re.search(
            r"(?:e-?way\s*bill\s*no\.?[:\s]*|\b)(\d{12})\b",
            text,
            re.IGNORECASE,
        )
        ewb_num = ewb_match.group(1) if ewb_match else "UNKNOWN_EWB"
        ewb_field = ExtractedField[str](
            value=ewb_num,
            raw_text=ewb_match.group(0) if ewb_match else None,
            confidence=0.98 if ewb_match else 0.40,
            bounding_box=find_box(r"\d{12}"),
            source_page=page_number,
            is_ambiguous=ewb_match is None,
            flag_reason="12-digit E-Way Bill number not detected" if not ewb_match else None,
        )

        # 2. Valid Upto / Expiry Date (PRD §4: printout 'Valid Upto' only)
        expiry_match = re.search(
            r"(?:valid\s*(?:upto|until|to)[:\s]*|\b)(\d{2}[-/\.]\d{2}[-/\.]\d{2,4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)",
            text,
            re.IGNORECASE,
        )
        expiry_field = (
            ExtractedField[str](
                value=expiry_match.group(1),
                raw_text=expiry_match.group(0),
                confidence=0.95,
                bounding_box=find_box(r"valid\s*upto"),
                source_page=page_number,
            )
            if expiry_match
            else None
        )

        # 3. Transporter Doc No (corresponds to LR number)
        doc_match = re.search(
            r"(?:trans(?:porter)?\s*doc(?:ument)?\.?\s*no\.?[:\s]*|\bdoc\s*no\.?[:\s]*)([A-Z0-9\-/]+)",
            text,
            re.IGNORECASE,
        )
        lr_field = (
            LRNormalizer.normalize(
                raw_text=doc_match.group(1),
                source_page=page_number,
                confidence=0.95,
                bounding_box=find_box(r"trans.*doc"),
            )
            if doc_match
            else None
        )

        # 4. Vehicle Number
        veh_match = re.search(
            r"(?:vehicle\s*no\.?[:\s]*|\b)([A-Z]{2}\s*\d{2}\s*[A-Z]{1,2}\s*\d{4})\b",
            text,
            re.IGNORECASE,
        )
        veh_clean = re.sub(r"\s+", "", veh_match.group(1).upper()) if veh_match else None
        veh_field = (
            ExtractedField[str](
                value=veh_clean,
                raw_text=veh_match.group(0),
                confidence=0.96,
                bounding_box=find_box(r"[A-Z]{2}\s*\d{2}\s*[A-Z]{1,2}\s*\d{4}"),
                source_page=page_number,
            )
            if veh_clean
            else None
        )

        # 5. Supply Type
        supply_match = re.search(
            r"(?:transaction\s*type|supply\s*type)[:\s]*([^\n]+)",
            text,
            re.IGNORECASE,
        )
        supply_type = supply_match.group(1).strip() if supply_match else None
        supply_field = (
            ExtractedField[str](
                value=supply_type,
                raw_text=supply_match.group(0) if supply_match else None,
                confidence=0.90,
                source_page=page_number,
            )
            if supply_type
            else None
        )

        return EwayBillData(
            eway_bill_number=ewb_field,
            valid_upto=expiry_field,
            transporter_doc_no=lr_field,
            vehicle_number=veh_field,
            supply_type=supply_field,
        )
