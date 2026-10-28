import re
from typing import Optional
from PIL import Image

from backend.app.schemas.erode_extraction import ErodeLRRow, ErodeLRSheet
from backend.app.services.grouping.range_expander import InvoiceRangeExpander
from backend.app.services.ocr.cropper import LRImageCropper


class ErodeLRSheetExtractor:
    """Extracts handwritten consignment rows, party names, invoice links, and totals from Erode LR sheets."""

    TRUCK_REGEX = re.compile(
        r"(?:truck\s*(?:no|number)|lorry\s*(?:no|number)|vehicle\s*no)[\s:]*([A-Za-z]{2}\s*\d{1,2}\s*[A-Za-z]{1,3}\s*\d{4})\b",
        re.IGNORECASE,
    )
    PLATE_REGEX = re.compile(r"\b([A-Za-z]{2}\s*\d{1,2}\s*[A-Za-z]{1,3}\s*\d{4})\b", re.IGNORECASE)
    DATE_REGEX = re.compile(
        r"\bdate[\s:]*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        re.IGNORECASE,
    )
    DEST_REGEX = re.compile(
        r"\bdestination[\s:]*([A-Za-z]+(?:\s+[A-Za-z]+)*?)(?=\s+date|\s*$|\n)",
        re.IGNORECASE,
    )

    OWNER_NAME_REGEX = re.compile(r"owner\s*name[\s:]*([A-Za-z\s.]+?)(?=\s+owner|\s+driver|\n|$)", re.IGNORECASE)
    OWNER_PHONE_REGEX = re.compile(r"owner\s*phone\s*(?:no)?[\s:]*(\d{10})", re.IGNORECASE)
    DRIVER_NAME_REGEX = re.compile(r"driver\s*name[\s:]*([A-Za-z\s.]+?)(?=\s+driver|\s+dl|\n|$)", re.IGNORECASE)
    DRIVER_PHONE_REGEX = re.compile(r"driver\s*phone\s*(?:no)?[\s:]*(\d{10})", re.IGNORECASE)
    DL_NO_REGEX = re.compile(r"dl\s*no[\s:]*([a-z0-9\s/-]+?)(?=\s+\d|\n|$)", re.IGNORECASE)

    # LR Line item matching
    LR_START_REGEX = re.compile(r"^\s*(?P<lr>2\d{4})\b\s*(?P<rest>.*)$", re.IGNORECASE)
    INVOICE_PATTERN = re.compile(r"\b(?:i\.\s*|inv[:\s]*)?(12\d{8}(?:[/-]\d{2,4})?)\b", re.IGNORECASE)
    PACKAGES_PATTERN = re.compile(r"\(?(\d+)\)?\s*(reels?|bundles?|bales?|boxes?|notebooks?)", re.IGNORECASE)
    WEIGHT_PATTERN = re.compile(r"\b(\d{4,6}(?:\.\d+)?)\b")
    DELIVERY_PATTERN = re.compile(r"delivery\s*(?:at|to)[\s:]*(.+?)(?=\n|$)", re.IGNORECASE)

    @classmethod
    def extract(
        cls,
        text: str,
        page_number: int = 1,
        page_image: Optional[Image.Image] = None,
        line_boxes: Optional[dict[str, list[float]]] = None,
    ) -> ErodeLRSheet:
        """Extracts complete handwritten LR sheet structure from OCR text with FR4 image cropping."""
        truck = cls._extract_truck(text)
        date_str = cls._extract_date(text)
        dest = cls._extract_dest(text)

        owner_name = cls._match_first(cls.OWNER_NAME_REGEX, text)
        owner_phone = cls._match_first(cls.OWNER_PHONE_REGEX, text)
        driver_name = cls._match_first(cls.DRIVER_NAME_REGEX, text)
        driver_phone = cls._match_first(cls.DRIVER_PHONE_REGEX, text)
        dl_no = cls._match_first(cls.DL_NO_REGEX, text)

        rows = cls._extract_rows(text, page_image, line_boxes)
        total_packs, total_wt = cls._extract_footer_totals(text)

        confidence = 0.95 if rows else 0.40

        return ErodeLRSheet(
            page_number=page_number,
            truck_number=truck,
            date=date_str,
            destination=dest,
            owner_name=owner_name,
            owner_phone=owner_phone,
            driver_name=driver_name,
            driver_phone=driver_phone,
            driver_license=dl_no,
            rows=rows,
            total_packages=total_packs,
            total_weight_kg=total_wt,
            confidence=round(confidence, 4),
        )

    @classmethod
    def _extract_truck(cls, text: str) -> Optional[str]:
        match = cls.TRUCK_REGEX.search(text)
        if match:
            return re.sub(r"\s+", "", match.group(1)).upper()
        plate_match = cls.PLATE_REGEX.search(text)
        if plate_match:
            return re.sub(r"\s+", "", plate_match.group(1)).upper()
        return None

    @classmethod
    def _extract_date(cls, text: str) -> Optional[str]:
        match = cls.DATE_REGEX.search(text)
        if match:
            raw = match.group(1).replace(".", "/").replace("-", "/")
            parts = raw.split("/")
            if len(parts) == 3:
                d, m, y = parts
                if len(y) == 2:
                    y = f"20{y}"
                return f"{int(d):02d}/{int(m):02d}/{y}"
        return None

    @classmethod
    def _extract_dest(cls, text: str) -> Optional[str]:
        m = cls.DEST_REGEX.search(text)
        if m:
            clean = re.sub(r"\s+", " ", m.group(1)).strip()
            clean = re.sub(r"\s*date.*$", "", clean, flags=re.IGNORECASE).strip()
            return clean if clean else None
        return None

    @classmethod
    def _match_first(cls, pattern: re.Pattern, text: str) -> Optional[str]:
        m = pattern.search(text)
        return m.group(1).strip() if m else None

    @classmethod
    def _extract_rows(
        cls,
        text: str,
        page_image: Optional[Image.Image] = None,
        line_boxes: Optional[dict[str, list[float]]] = None,
    ) -> list[ErodeLRRow]:
        rows: list[ErodeLRRow] = []
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        current_block: list[str] = []
        current_lr: Optional[str] = None

        for line in lines:
            m = cls.LR_START_REGEX.match(line)
            if m:
                # If we were already tracking an LR block, parse it
                if current_lr and current_block:
                    parsed_row = cls._parse_lr_block(current_lr, current_block, page_image, line_boxes)
                    if parsed_row:
                        rows.append(parsed_row)
                current_lr = m.group("lr")
                current_block = [m.group("rest")]
            elif current_lr:
                # Stop if we hit footer totals line
                if re.match(r"^[-–—_]{5,}$", line) or re.search(r"\b(?:total|signature)\b", line, re.IGNORECASE):
                    parsed_row = cls._parse_lr_block(current_lr, current_block, page_image, line_boxes)
                    if parsed_row:
                        rows.append(parsed_row)
                    current_lr = None
                    current_block = []
                else:
                    current_block.append(line)

        if current_lr and current_block:
            parsed_row = cls._parse_lr_block(current_lr, current_block, page_image, line_boxes)
            if parsed_row:
                rows.append(parsed_row)

        return rows

    @classmethod
    def _parse_lr_block(
        cls,
        lr_no: str,
        block_lines: list[str],
        page_image: Optional[Image.Image] = None,
        line_boxes: Optional[dict[str, list[float]]] = None,
    ) -> Optional[ErodeLRRow]:
        full_block_text = " ".join(block_lines)

        # 1. Invoice extraction
        raw_inv = ""
        inv_match = cls.INVOICE_PATTERN.search(full_block_text)
        if inv_match:
            raw_inv = inv_match.group(1)
        expanded_invoices = InvoiceRangeExpander.expand(raw_inv).expanded_numbers if raw_inv else []

        # 2. Package extraction
        pack_match = cls.PACKAGES_PATTERN.search(full_block_text)
        pack_count = int(pack_match.group(1)) if pack_match else None
        pack_type = pack_match.group(2).lower() if pack_match else "reels"
        pack_str = f"{pack_count} {pack_type}" if pack_count else "Unknown"

        # 3. Weight extraction (look for weight in kg, usually the trailing number)
        weight_matches = cls.WEIGHT_PATTERN.findall(full_block_text)
        weight_val = None
        for w_str in reversed(weight_matches):
            try:
                candidate = float(w_str)
                # Typical consignment weights are 500 kg to 35,000 kg
                if 100.0 <= candidate <= 50000.0 and w_str not in expanded_invoices:
                    weight_val = candidate
                    break
            except ValueError:
                continue

        # 4. Delivery location / Party separation
        delivery_match = cls.DELIVERY_PATTERN.search(full_block_text)
        delivery_to = delivery_match.group(1).strip() if delivery_match else None

        # Party name is usually in the first line of the block
        party_name = block_lines[0]
        # Clean out package/weight/invoice tokens from party name
        party_name = cls.PACKAGES_PATTERN.sub("", party_name)
        party_name = cls.WEIGHT_PATTERN.sub("", party_name)
        party_name = cls.INVOICE_PATTERN.sub("", party_name)
        party_name = re.sub(r"delivery\s*(?:at|to).*$", "", party_name, flags=re.IGNORECASE).strip()

        # 5. FR4: Crop handwritten LR number snippet if image and bbox available
        lr_crop = None
        lr_bbox = line_boxes.get(lr_no) if line_boxes else None
        if page_image and lr_bbox:
            lr_crop = LRImageCropper.crop_bounding_box_base64(page_image, lr_bbox)

        return ErodeLRRow(
            lr_number=lr_no,
            party_name=party_name or "Unknown Party",
            delivery_to=delivery_to,
            raw_invoice_text=raw_inv,
            invoices=expanded_invoices,
            packages_str=pack_str,
            package_count=pack_count,
            package_type=pack_type,
            weight_kg=weight_val,
            lr_crop_base64=lr_crop,
            bbox=lr_bbox,
            confidence=0.95,
        )

    @classmethod
    def _extract_footer_totals(cls, text: str) -> tuple[Optional[int], Optional[float]]:
        packs = None
        wt = None
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        # Check last 3 lines for totals
        for line in reversed(lines[-4:]):
            nums = re.findall(r"\b\d+(?:\.\d+)?\b", line)
            if len(nums) >= 2:
                try:
                    p = int(nums[0])
                    w = float(nums[1])
                    if 1 <= p <= 500 and 1000.0 <= w <= 60000.0:
                        packs = p
                        wt = w
                        break
                except ValueError:
                    continue
        return packs, wt

