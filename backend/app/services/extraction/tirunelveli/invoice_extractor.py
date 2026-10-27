import re
from typing import Optional

from backend.app.schemas.document import OCRLineResult
from backend.app.schemas.extraction import ExtractedField, MaterialInvoiceData
from backend.app.services.extraction.tirunelveli.lr_normalizer import LRNormalizer


class MaterialInvoiceExtractor:
    """Extracts raw fields from Tirunelveli Material Invoices ('Tax Invoice - Transport Copy')."""

    @classmethod
    def extract(
        cls,
        text: str,
        page_number: int,
        bounding_boxes: Optional[list[OCRLineResult]] = None,
    ) -> MaterialInvoiceData:
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        def find_box(pattern: str) -> Optional[list[list[float]]]:
            if not bounding_boxes:
                return None
            for item in bounding_boxes:
                if re.search(pattern, item.text, re.IGNORECASE):
                    return item.box
            return None

        # 1. Invoice Number (10 digits starting with 225... or explicit label)
        inv_no_match = re.search(
            r"(?:invoice\s*no\.?[:\s]*|\b)(225\d{7}|\d{10})\b",
            text,
            re.IGNORECASE,
        )
        inv_no_str = inv_no_match.group(1) if inv_no_match else "UNKNOWN_INV"
        inv_field = ExtractedField[str](
            value=inv_no_str,
            raw_text=inv_no_match.group(0) if inv_no_match else None,
            confidence=0.98 if inv_no_match else 0.40,
            bounding_box=find_box(r"225\d{7}|\d{10}"),
            source_page=page_number,
            is_ambiguous=inv_no_match is None,
            flag_reason="Invoice number not detected with high confidence" if not inv_no_match else None,
        )

        # 2. Invoice Date
        date_match = re.search(
            r"(?:date[:\s]*|\b)(\d{2}[-/\.]\d{2}[-/\.]\d{2,4})\b",
            text,
            re.IGNORECASE,
        )
        date_str = date_match.group(1) if date_match else "UNKNOWN_DATE"
        date_field = ExtractedField[str](
            value=date_str,
            raw_text=date_match.group(0) if date_match else None,
            confidence=0.95 if date_match else 0.40,
            bounding_box=find_box(r"\d{2}[-/\.]\d{2}[-/\.]\d{2,4}"),
            source_page=page_number,
            is_ambiguous=date_match is None,
            flag_reason="Invoice date missing or unreadable" if not date_match else None,
        )

        # 3. Vehicle Number (e.g. TN52Y7426)
        veh_match = re.search(
            r"(?:vehicle(?:\s*no)?\.?[:\s]*|\b)([A-Z]{2}\s*\d{2}\s*[A-Z]{1,2}\s*\d{4})\b",
            text,
            re.IGNORECASE,
        )
        veh_clean = re.sub(r"\s+", "", veh_match.group(1).upper()) if veh_match else "UNKNOWN_VEHICLE"
        veh_field = ExtractedField[str](
            value=veh_clean,
            raw_text=veh_match.group(0) if veh_match else None,
            confidence=0.96 if veh_match else 0.40,
            bounding_box=find_box(r"[A-Z]{2}\s*\d{2}\s*[A-Z]{1,2}\s*\d{4}"),
            source_page=page_number,
            is_ambiguous=veh_match is None,
            flag_reason="Vehicle plate number missing on invoice" if not veh_match else None,
        )

        # 4. Printed LR Number (e.g., LR No: 019427 or 19427)
        lr_match = re.search(
            r"(?:lr\s*no\.?[:\s]*|lorry\s*receipt\s*no\.?[:\s]*|\blr\s*#?\s*)(\d{4,8})\b",
            text,
            re.IGNORECASE,
        )
        lr_field = (
            LRNormalizer.normalize(
                raw_text=lr_match.group(1),
                source_page=page_number,
                confidence=0.95,
                bounding_box=find_box(r"\blr\b|\blorry\s*receipt\b"),
            )
            if lr_match
            else None
        )

        # 5. E-Way Bill Number (12 digits)
        ewb_match = re.search(
            r"(?:ewb(?:\s*no)?\.?[:\s]*|e-?way\s*bill\s*no\.?[:\s]*|\b)(\d{12})\b",
            text,
            re.IGNORECASE,
        )
        ewb_field = (
            ExtractedField[str](
                value=ewb_match.group(1),
                raw_text=ewb_match.group(0),
                confidence=0.97,
                bounding_box=find_box(r"\d{12}"),
                source_page=page_number,
            )
            if ewb_match
            else None
        )

        # 6. Bill To Party
        bill_to_match = re.search(
            r"bill\s*to[:\s]*([^\n]+(?:\n[^\n]+){1,3}?)(?=(?:ship\s*to|gstin|pan|state|$))",
            text,
            re.IGNORECASE,
        )
        bill_to_text = (
            " ".join(bill_to_match.group(1).split())
            if bill_to_match
            else "UNKNOWN_BILL_TO"
        )
        bill_to_field = ExtractedField[str](
            value=bill_to_text,
            raw_text=bill_to_match.group(0) if bill_to_match else None,
            confidence=0.90 if bill_to_match else 0.40,
            bounding_box=find_box(r"bill\s*to"),
            source_page=page_number,
        )

        # 7. Ship To Party
        ship_to_match = re.search(
            r"ship\s*to[:\s]*([^\n]+(?:\n[^\n]+){1,3}?)(?=(?:product|description|sl|item|$))",
            text,
            re.IGNORECASE,
        )
        ship_to_text = (
            " ".join(ship_to_match.group(1).split())
            if ship_to_match
            else bill_to_text
        )
        ship_to_field = ExtractedField[str](
            value=ship_to_text,
            raw_text=ship_to_match.group(0) if ship_to_match else None,
            confidence=0.90 if ship_to_match else 0.40,
            bounding_box=find_box(r"ship\s*to"),
            source_page=page_number,
        )

        # 8. Packages Description & Count
        pkg_match = re.search(
            r"(?:packages?|packs?|bundles?|reels?)[:\s]*(\d+)\s*([a-zA-Z]+)",
            text,
            re.IGNORECASE,
        )
        pkg_count = int(pkg_match.group(1)) if pkg_match else 0
        pkg_desc = f"{pkg_count} {pkg_match.group(2).lower()}" if pkg_match else "0 packages"
        pkg_desc_field = ExtractedField[str](
            value=pkg_desc,
            raw_text=pkg_match.group(0) if pkg_match else None,
            confidence=0.92 if pkg_match else 0.40,
            source_page=page_number,
        )
        pkg_count_field = ExtractedField[int](
            value=pkg_count,
            raw_text=str(pkg_count),
            confidence=0.92 if pkg_match else 0.40,
            source_page=page_number,
        )

        # 9. Gross Weight (Governing Weight) & Net Weight
        gross_match = re.search(
            r"(?:gross\s*wt\.?|gross\s*weight)[:\s]*([\d\.,]+)",
            text,
            re.IGNORECASE,
        )
        gross_wt = (
            float(gross_match.group(1).replace(",", ""))
            if gross_match
            else 0.0
        )
        gross_field = ExtractedField[float](
            value=gross_wt,
            raw_text=gross_match.group(0) if gross_match else None,
            confidence=0.95 if gross_match else 0.30,
            bounding_box=find_box(r"gross\s*wt"),
            source_page=page_number,
            is_ambiguous=gross_wt == 0.0,
            flag_reason="Gross weight missing on invoice" if gross_wt == 0.0 else None,
        )

        net_match = re.search(
            r"(?:net\s*wt\.?|net\s*weight)[:\s]*([\d\.,]+)",
            text,
            re.IGNORECASE,
        )
        net_wt = (
            float(net_match.group(1).replace(",", ""))
            if net_match
            else gross_wt
        )
        net_field = ExtractedField[float](
            value=net_wt,
            raw_text=net_match.group(0) if net_match else None,
            confidence=0.95 if net_match else 0.30,
            source_page=page_number,
        )

        # 10. Freight Amount ("Add: Frieght" / "Add: Freight")
        # PRD §5.4: Amount 0 = party freight (dealer pays); amount above 0 = shipper pays
        frt_match = re.search(
            r"(?:add[:\s]*frie?ght|freight\s*charges?)[:\s]*([\d\.,]+)",
            text,
            re.IGNORECASE,
        )
        frt_val = (
            float(frt_match.group(1).replace(",", ""))
            if frt_match
            else 0.0
        )
        frt_field = ExtractedField[float](
            value=frt_val,
            raw_text=frt_match.group(0) if frt_match else "0.0 (Party Freight)",
            confidence=0.95 if frt_match else 0.90,  # 0.0 is common and expected for party freight
            bounding_box=find_box(r"frie?ght"),
            source_page=page_number,
        )

        # 11. Net Claim Rs / Invoice Total
        claim_match = re.search(
            r"(?:net\s*claim\s*rs\.?|total\s*(?:invoice)?\s*value|total\s*amount)[:\s]*([\d\.,]+)",
            text,
            re.IGNORECASE,
        )
        claim_val = (
            float(claim_match.group(1).replace(",", ""))
            if claim_match
            else 0.0
        )
        claim_field = ExtractedField[float](
            value=claim_val,
            raw_text=claim_match.group(0) if claim_match else None,
            confidence=0.95 if claim_match else 0.40,
            bounding_box=find_box(r"net\s*claim"),
            source_page=page_number,
        )

        return MaterialInvoiceData(
            invoice_number=inv_field,
            invoice_date=date_field,
            vehicle_number=veh_field,
            printed_lr_number=lr_field,
            eway_bill_number=ewb_field,
            bill_to_party=bill_to_field,
            ship_to_party=ship_to_field,
            packages_description=pkg_desc_field,
            package_count=pkg_count_field,
            net_weight_kg=net_field,
            gross_weight_kg=gross_field,
            freight_amount=frt_field,
            net_claim_rs=claim_field,
        )
