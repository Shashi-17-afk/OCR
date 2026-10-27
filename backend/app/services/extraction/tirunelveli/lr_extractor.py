import re
from typing import Optional

from backend.app.schemas.document import OCRLineResult
from backend.app.schemas.extraction import ExtractedField, LorryReceiptData
from backend.app.services.extraction.tirunelveli.lr_normalizer import LRNormalizer


class LorryReceiptExtractor:
    """Extracts raw fields from Tirunelveli Lorry Receipts (LR).

    PRD §3.2 & §4:
    - LR number is printed (e.g. '019427' or '19427').
    - Truck number, date, consignee, delivery place, packages, weight, invoices are recorded.
    - Pre-printed freight box text 'TO BE BILLED / UNLOADING BY CONSIGNEE' is explicitly ignored.
    - LR weight is recorded strictly for cross-checking; invoice weight governs.
    """

    @classmethod
    def extract(
        cls,
        text: str,
        page_number: int,
        bounding_boxes: Optional[list[OCRLineResult]] = None,
    ) -> LorryReceiptData:
        def find_box(pattern: str) -> Optional[list[list[float]]]:
            if not bounding_boxes:
                return None
            for item in bounding_boxes:
                if re.search(pattern, item.text, re.IGNORECASE):
                    return item.box
            return None

        # 1. Printed LR Number (e.g. N° 019427, LR No. 019406)
        lr_match = re.search(
            r"(?:n[°o\.]?\s*[:\s]*|lr\s*no\.?[:\s]*|consignment\s*note\s*no\.?[:\s]*)(\d{4,8})\b",
            text,
            re.IGNORECASE,
        )
        if not lr_match:
            # Fallback for standalone printed 5-6 digit numbers near header
            lr_match = re.search(r"\b(0\d{5}|\d{5,6})\b", text)

        lr_field = (
            LRNormalizer.normalize(
                raw_text=lr_match.group(1),
                source_page=page_number,
                confidence=0.96,
                bounding_box=find_box(r"n[°o\.]|0\d{5}"),
            )
            if lr_match
            else LRNormalizer.normalize(
                raw_text="UNKNOWN_LR",
                source_page=page_number,
                confidence=0.20,
            )
        )

        # 2. Truck Number (e.g. TN52Y7426, TN 52 Y 7426)
        truck_match = re.search(
            r"(?:truck\s*(?:number|no)?\.?[:\s]*|vehicle\s*no\.?[:\s]*|\b)([A-Z]{2}\s*\d{1,2}\s*[A-Z]{1,2}\s*\d{4})\b",
            text,
            re.IGNORECASE,
        )
        truck_clean = (
            re.sub(r"\s+", "", truck_match.group(1).upper())
            if truck_match
            else "UNKNOWN_TRUCK"
        )
        truck_field = ExtractedField[str](
            value=truck_clean,
            raw_text=truck_match.group(0) if truck_match else None,
            confidence=0.94 if truck_match else 0.40,
            bounding_box=find_box(r"[A-Z]{2}\s*\d{1,2}\s*[A-Z]{1,2}\s*\d{4}"),
            source_page=page_number,
            is_ambiguous=truck_match is None,
            flag_reason="Truck number not found on LR" if not truck_match else None,
        )

        # 3. Booking Date
        date_match = re.search(
            r"(?:date[:\s]*|\b)(\d{2}[-/\.]\d{2}[-/\.]\d{2,4})\b",
            text,
            re.IGNORECASE,
        )
        date_str = date_match.group(1) if date_match else "UNKNOWN_DATE"
        date_field = ExtractedField[str](
            value=date_str,
            raw_text=date_match.group(0) if date_match else None,
            confidence=0.92 if date_match else 0.40,
            source_page=page_number,
        )

        # 4. Consignor
        consignor_match = re.search(
            r"consignor(?:['’]?s?\s*name(?:\s*&\s*address)?)?[:\s]*([^\n]+)",
            text,
            re.IGNORECASE,
        )
        consignor_str = (
            consignor_match.group(1).strip()
            if consignor_match
            else "SPB Ltd Tirunelveli"
        )
        consignor_field = ExtractedField[str](
            value=consignor_str,
            raw_text=consignor_match.group(0) if consignor_match else None,
            confidence=0.90,
            source_page=page_number,
        )

        # 5. Consignee
        consignee_match = re.search(
            r"consignee(?:['’]?s?\s*name(?:\s*&\s*address)?)?[:\s]*([^\n]+)",
            text,
            re.IGNORECASE,
        )
        consignee_str = (
            consignee_match.group(1).strip()
            if consignee_match
            else "UNKNOWN_CONSIGNEE"
        )
        consignee_field = ExtractedField[str](
            value=consignee_str,
            raw_text=consignee_match.group(0) if consignee_match else None,
            confidence=0.90 if consignee_match else 0.40,
            source_page=page_number,
        )

        # 6. Delivery Place / Unloading Point
        del_match = re.search(
            r"(?:delivery\s*(?:place|at(?:\s*/?\s*to)?|destination)|unloading\s*point)[:\s]*[\r\n\s]*([^\n]+)",
            text,
            re.IGNORECASE,
        )
        del_str = del_match.group(1).strip() if del_match else consignee_str
        del_field = ExtractedField[str](
            value=del_str,
            raw_text=del_match.group(0) if del_match else None,
            confidence=0.90 if del_match else 0.40,
            source_page=page_number,
        )

        # 7. Packages Description
        pkg_match = re.search(
            r"(?:no\s*of\s*packages|packages?|description\s*of\s*goods)[:\s]*([^\n]+)",
            text,
            re.IGNORECASE,
        )
        pkg_str = pkg_match.group(1).strip() if (pkg_match and pkg_match.group(1).strip()) else ""
        if not pkg_str or pkg_str == "0 packages":
            tbl_pkg = re.search(r"CONSIGNMENT\s*SUMMARY[\s\S]*?(?:Packages|Gross\s*Wt)[\s\S]*?(\d+)\s+([\d,]+\.\d{2})", text, re.IGNORECASE)
            if tbl_pkg:
                pkg_str = f"{tbl_pkg.group(1)} packages"
            else:
                pkg_str = "0 packages"

        pkg_field = ExtractedField[str](
            value=pkg_str,
            raw_text=pkg_match.group(0) if pkg_match else None,
            confidence=0.88 if pkg_match else 0.35,
            source_page=page_number,
        )

        # 8. LR Weight (kg) - Strictly Cross-Check Weight per PRD
        wt_match = re.search(
            r"(?:gross\s*wt(?:\(kg\))?|weight(?:\s*in\s*kgs?)?)[:\s]*[\r\n\s]*(\d+[\d,]*\.?\d*)",
            text,
            re.IGNORECASE,
        )
        lr_wt = 0.0
        if wt_match and wt_match.group(1):
            try:
                lr_wt = float(wt_match.group(1).replace(",", ""))
            except ValueError:
                lr_wt = 0.0

        if lr_wt == 0.0:
            tbl_wt = re.search(r"\b(\d{4,6}\.\d{2})\b", text)
            if tbl_wt:
                try:
                    lr_wt = float(tbl_wt.group(1).replace(",", ""))
                except ValueError:
                    lr_wt = 0.0

        wt_field = ExtractedField[float](
            value=lr_wt,
            raw_text=wt_match.group(0) if wt_match else None,
            confidence=0.90 if lr_wt > 0.0 else 0.30,
            source_page=page_number,
            flag_reason="LR weight is a cross-check only; invoice weight governs (PRD §2)",
        )

        # 9. Invoice Numbers (handwritten reference string, e.g. "Inv: 2250601397 to 1400" or "2250601397-1400")
        inv_ref_match = re.search(
            r"(?:inv(?:oices?)?[:\s]*|inv(?:oice)?\s*nos?\.?[:\s]*)([^\r\n]+)",
            text,
            re.IGNORECASE,
        )
        inv_ref_str = ""
        if inv_ref_match:
            raw_inv_line = inv_ref_match.group(1).strip()
            # Strip trailing preprinted boilerplate if on same line
            raw_inv_line = re.split(r"\bto\s+be\s+billed\b", raw_inv_line, flags=re.IGNORECASE)[0].strip()
            inv_ref_str = raw_inv_line

        if not inv_ref_str or not any(c.isdigit() for c in inv_ref_str):
            direct_range = re.search(r"\b(225\d{7}(?:\s*(?:to|-|–)\s*(?:225\d{7}|\d{2,4}))?)\b", text)
            if direct_range:
                inv_ref_str = direct_range.group(1).strip()

        inv_ref_field = ExtractedField[str](
            value=inv_ref_str,
            raw_text=inv_ref_match.group(0) if inv_ref_match else None,
            confidence=0.90 if inv_ref_str else 0.40,
            source_page=page_number,
            is_ambiguous=not inv_ref_str,
            flag_reason="No invoice reference found on LR" if not inv_ref_str else None,
        )

        # 10. Value
        val_match = re.search(
            r"(?:declared\s*value(?:\s*\(rs\))?|total\s*value|value)[^\d\n]*[\r\n\s]*([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        val_num = None
        if val_match and val_match.group(1):
            try:
                candidate = float(val_match.group(1).replace(",", ""))
                if candidate > 0.0:
                    val_num = candidate
            except ValueError:
                val_num = None

        val_field = (
            ExtractedField[float](
                value=val_num,
                raw_text=val_match.group(0),
                confidence=0.90,
                source_page=page_number,
            )
            if val_num is not None
            else None
        )

        return LorryReceiptData(
            lr_number=lr_field,
            truck_number=truck_field,
            date=date_field,
            consignor=consignor_field,
            consignee=consignee_field,
            delivery_place=del_field,
            packages_description=pkg_field,
            weight_kg=wt_field,
            invoice_numbers_raw=inv_ref_field,
            total_value_rs=val_field,
            preprinted_freight_ignored=True,
        )
