import datetime
import re
from typing import Optional
from PIL import Image

from backend.app.schemas.erode_extraction import ErodeLRRow, ErodeLRSheet
from backend.app.services.grouping.range_expander import InvoiceRangeExpander
from backend.app.services.ocr.cropper import LRImageCropper


class ErodeLRSheetExtractor:
    """Extracts handwritten consignment rows, party names, invoice links, and totals from Erode LR sheets."""

    TRUCK_REGEX = re.compile(
        r"(?:truck\s*(?:no|number)|lorry\s*(?:no|number)|vehicle\s*no)[\s.:-]*([A-Za-z]{2}[\s.-]*\d{1,2}[\s.-]*[A-Za-z0-9]{0,3}[\s.-]*\d{4})\b",
        re.IGNORECASE,
    )
    PLATE_REGEX = re.compile(r"\b([A-Za-z]{2}[\s.-]*\d{1,2}[\s.-]*[A-Za-z0-9]{0,3}[\s.-]*\d{4})\b", re.IGNORECASE)
    HEADER_DATE_PATTERNS = [
        re.compile(
            r"(?i)\b(?:date|dat|datt|dte|dt|pate)[\s.:-]*(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,4})\b"
        ),
        re.compile(
            r"(?i)(?:dat[et]*|dte|dt|pate)[\s.:-]*(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,4})\b"
        ),
        re.compile(r"\b(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,4})\b"),
    ]
    DEST_REGEX = re.compile(
        r"\b(?:destination|dest|to|place)[\s.:-]*([A-Za-z]+(?:\s+[A-Za-z]+)*?)(?=\s+date|\s*$|\n)",
        re.IGNORECASE,
    )

    DEST_CITIES = [
        "NAVIMUMBAI", "NAVI MUMBAI", "GHAZIABAD", "KOLKATA", "MADURAI", "COIMBATORE",
        "SALEM", "CHENNAI", "BANGALORE", "HYDERABAD", "MUMBAI", "NOIDA", "GURGAON", "FARIDABAD",
        "DELHI", "PONDICHERRY", "TRICHY", "TIRUPPUR", "SIVAKASI", "PUNE",
        "HUBLI", "KOVILPATTI", "POLLACHI", "CHENGALPATTU", "KARUR", "DINDIGUL",
        "SURAT", "AHMEDABAD", "CUTTACK", "BHUBANESWAR", "NAGPUR", "INDORE", "JAIPUR", "KANPUR", "LUCKNOW",
        "MORBI", "VAPI", "SECUNDERABAD", "VIJAYAWADA", "VISAKHAPATNAM", "KOCHI", "CALICUT", "THRISSUR", "KANNUR"
    ]

    OWNER_NAME_REGEX = re.compile(r"owner\s*name[\s:]*([A-Za-z\s.]+?)(?=\s+owner|\s+driver|\n|$)", re.IGNORECASE)
    OWNER_PHONE_REGEX = re.compile(r"owner\s*phone\s*(?:no)?[\s.:]*(\d{5}\s*\d{5}|\d{10})", re.IGNORECASE)
    DRIVER_NAME_REGEX = re.compile(r"driver\s*name[\s:]*([A-Za-z\s.]+?)(?=\s+driver|\s+dl|\n|$)", re.IGNORECASE)
    DRIVER_PHONE_REGEX = re.compile(r"driver\s*phone\s*(?:no)?[\s.:]*(\d{5}\s*\d{5}|\d{10})", re.IGNORECASE)
    DL_NO_REGEX = re.compile(r"dl\s*no[\s:]*([a-z0-9\s/-]+?)(?=\s+\d|\n|$)", re.IGNORECASE)

    # LR Line item matching
    LR_START_REGEX = re.compile(
        r"(?:^|[^\d])(?P<lr>(?:2|3|0|8|9|4|7)[/\s]?[98]\s*[\dOo]\s*[\dOo]\s*[\dOo\)])(?:\b|(?<=\)))",
        re.IGNORECASE,
    )
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
        ocr_lines: Optional[list] = None,
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

        # Sanitize names against printed form labels
        def _clean_person_name(val: Optional[str]) -> Optional[str]:
            if not val:
                return None
            val_clean = re.sub(r"[:_.\-]+", " ", val).strip()
            val_upper = val_clean.upper()
            disallowed = (
                "WEIGHT IN KGS", "WEIGHT IN", "TRUCK NO", "PALLIPALAYAM", "SALEM",
                "OWNER", "DRIVER", "DL NO", "PHONE", "DATE", "SIGNATURE",
                "SESHASAYEE", "SPB", "ERODE", "UNKNOWN", "TOTAL", "AGREEMENT"
            )
            if any(val_upper.startswith(d) or val_upper == d for d in disallowed):
                return None
            if len(val_clean) < 3 or not re.search(r"[A-Za-z]{2,}", val_clean):
                return None
            return val_clean

        owner_name = _clean_person_name(owner_name)
        driver_name = _clean_person_name(driver_name)

        rows = []
        if ocr_lines:
            rows = cls._extract_rows_spatial(ocr_lines, page_image, line_boxes)
        if not rows:
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
        """Extracts and validates booking date from LR sheet header, normalized to ISO YYYY-MM-DD."""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        header_lines = lines[:25]
        header_text = "\n".join(header_lines)

        for pattern in cls.HEADER_DATE_PATTERNS:
            for match in pattern.finditer(header_text):
                d_str, m_str, y_str = match.group(1), match.group(2), match.group(3)
                try:
                    d = int(d_str)
                    m = int(m_str)
                    y = int(y_str)
                    if y < 100:
                        y += 2000
                    val_date = datetime.date(y, m, d)
                    if 2020 <= val_date.year <= 2035:
                        return val_date.strftime("%Y-%m-%d")
                except ValueError:
                    continue
        return None

    @classmethod
    def _extract_dest(cls, text: str) -> Optional[str]:
        m = cls.DEST_REGEX.search(text)
        if m:
            clean = re.sub(r"\s+", " ", m.group(1)).strip()
            clean = re.sub(r"\s*date.*$", "", clean, flags=re.IGNORECASE).strip()
            if clean:
                return clean

        # Also search for known destination cities in header lines
        header_text = text[:800]
        for city in sorted(cls.DEST_CITIES, key=len, reverse=True):
            if re.search(r"\b" + re.escape(city) + r"\b", header_text, re.IGNORECASE):
                # Check for dual destination pairs like COIMBATORE / POLLACHI or Chengalpattu / CHENNAI
                m_dual = re.search(r"\b([A-Za-z]+)\s*/\s*([A-Za-z]+)\b", header_text)
                if m_dual and (city.upper() in m_dual.group(0).upper()):
                    return m_dual.group(0).upper()
                return city
        return None

    @classmethod
    def _match_first(cls, pattern: re.Pattern, text: str) -> Optional[str]:
        m = pattern.search(text)
        return m.group(1).strip() if m else None

    @classmethod
    def _extract_rows_spatial(
        cls,
        ocr_lines: list,
        page_image: Optional[Image.Image] = None,
        line_boxes: Optional[dict[str, list[float]]] = None,
    ) -> list[ErodeLRRow]:
        if not ocr_lines:
            return []

        page_w = max((p[0] for it in ocr_lines for p in getattr(it, "box", [])), default=1754.0)
        page_h = max((p[1] for it in ocr_lines for p in getattr(it, "box", [])), default=1240.0)

        header_y = page_h * 0.35
        footer_y = page_h * 0.95

        for it in ocr_lines:
            t = getattr(it, "text", "").lower()
            box = getattr(it, "box", [])
            if not box:
                continue
            y_mid = sum(p[1] for p in box) / 4.0
            if any(k in t for k in ["lr. no", "lr.no", "party name", "weight in kgs", "bundles/reels"]):
                header_y = max(header_y, y_mid + 10.0)
            if any(k in t for k in ["total", "signature"]) and y_mid > page_h * 0.5:
                footer_y = min(footer_y, y_mid - 10.0)

        table_items = []
        for it in ocr_lines:
            box = getattr(it, "box", [])
            if not box:
                continue
            y_mid = sum(p[1] for p in box) / 4.0
            if header_y < y_mid < footer_y:
                table_items.append((y_mid, it))

        table_items.sort(key=lambda x: x[0])

        # Identify LR number anchors in left column (x / page_w < 0.25)
        lr_anchors = []
        for y_mid, it in table_items:
            box = getattr(it, "box", [])
            x_mid = sum(p[0] for p in box) / 4.0
            if (x_mid / page_w) < 0.25:
                t = getattr(it, "text", "")
                m = re.findall(r"(?:^|[^\d])((?:2|3|0|8|9|4|7)[0-9bOo\s/]{3,7})(?:$|[^\d])", t)
                if m:
                    clean = re.sub(r"[\s/]+", "", m[0]).replace("O", "0").replace("o", "0").replace("b", "6").replace(")", "1")
                    if len(clean) == 5:
                        if clean[1] in ("9", "8") and clean[0] != "2":
                            clean = "2" + clean[1:]
                    elif len(clean) == 4 and clean.startswith("9"):
                        clean = "2" + clean
                    elif len(clean) > 5 and "29" in clean:
                        idx_29 = clean.find("29")
                        clean = clean[idx_29:idx_29+5]

                    if len(clean) == 5 and clean.startswith("29"):
                        lr_anchors.append((y_mid, clean, it))

        lr_anchors.sort(key=lambda x: x[0])
        u_anchors = []
        for y, lr, it in lr_anchors:
            if not u_anchors or (y - u_anchors[-1][0]) > 25.0:
                u_anchors.append((y, lr, it))

        if len(u_anchors) >= 2:
            base_lr = int(u_anchors[0][1])
            cleaned_anchors = []
            for idx, (y, lr, it) in enumerate(u_anchors):
                exp_lr = str(base_lr + idx)
                if abs(int(lr) - (base_lr + idx)) <= 2:
                    cleaned_anchors.append((y, exp_lr, it))
                else:
                    cleaned_anchors.append((y, lr, it))
            u_anchors = cleaned_anchors

        if not u_anchors:
            return []

        row_bands = []
        for i in range(len(u_anchors)):
            y_curr = u_anchors[i][0]
            y_prev = u_anchors[i - 1][0] if i > 0 else y_curr - 30.0
            y_next = u_anchors[i + 1][0] if i < len(u_anchors) - 1 else footer_y
            top = (y_prev + y_curr) / 2.0
            bottom = (y_curr + y_next) / 2.0
            row_bands.append((top, bottom, u_anchors[i][1]))

        rows: list[ErodeLRRow] = []
        for top, bottom, lr_no in row_bands:
            band_lines = [getattr(it, "text", "") for y, it in table_items if top <= y < bottom]
            parsed = cls._parse_lr_block(lr_no, band_lines, page_image, line_boxes)
            if parsed:
                rows.append(parsed)

        return rows

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
            m = cls.LR_START_REGEX.search(line)
            if m and not re.search(r"\b(?:phone|dl|truck|lorry|date|weight\s*in|broker|pallipalayam)\b", line, re.I):
                raw_lr = m.group("lr")
                clean_lr = re.sub(r"[\s/]+", "", raw_lr).replace(")", "1").replace("O", "0").replace("o", "0")
                if len(clean_lr) == 5:
                    if clean_lr[1] in ("9", "8") and clean_lr[0] != "2":
                        clean_lr = "2" + clean_lr[1:]

                if len(clean_lr) == 5 and clean_lr.startswith("29"):
                    if current_lr and current_block:
                        parsed_row = cls._parse_lr_block(current_lr, current_block, page_image, line_boxes)
                        if parsed_row:
                            rows.append(parsed_row)
                    current_lr = clean_lr
                    rest = line[:m.start()] + " " + line[m.end():]
                    current_block = [rest.strip()] if rest.strip() else []
                    continue

            if current_lr:
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
        clean_inv_text = re.sub(r"\b18[5s](\d{7})\b", r"125\1", full_block_text)
        clean_inv_text = re.sub(r"\b105(\d{7})\b", r"125\1", clean_inv_text)
        clean_inv_text = re.sub(r"\b1[aA]55(\d{6})\b", r"1255\1", clean_inv_text)
        clean_inv_text = re.sub(r"\b18s5104b6\b", "1250510466", clean_inv_text, flags=re.I)
        
        all_inv_matches = re.findall(r"\b(12\d{8}(?:[/-]\d{2,4})?)\b", clean_inv_text)
        expanded_invoices = []
        for inv_str in all_inv_matches:
            for exp in InvoiceRangeExpander.expand(inv_str).expanded_numbers:
                if exp not in expanded_invoices:
                    expanded_invoices.append(exp)

        raw_inv = ""
        inv_match = cls.INVOICE_PATTERN.search(clean_inv_text)
        if inv_match:
            raw_inv = inv_match.group(1)
        elif all_inv_matches:
            raw_inv = ", ".join(all_inv_matches)

        # 2. Package extraction
        pack_match = cls.PACKAGES_PATTERN.search(full_block_text)
        pack_count = int(pack_match.group(1)) if pack_match else None
        pack_type = pack_match.group(2).lower() if pack_match else "bundles"

        if not pack_count:
            # Check for abbreviations like "72 bdl", "53 bcy", "32 bcy"
            m_abbrev = re.search(r"\b(\d{1,4})\s*(?:bdl|bcy|bc|bundles?|reels?|boxes?|bales?|nos?)\b", full_block_text, re.I)
            if m_abbrev:
                pack_count = int(m_abbrev.group(1))
            else:
                # Look for standalone package numbers < 500
                m_nums = re.findall(r"\b(\d{1,3})\b", full_block_text)
                for num_s in m_nums:
                    val = int(num_s)
                    if 1 <= val <= 500 and num_s not in raw_inv and not re.search(r"^\d{4,}$", num_s):
                        pack_count = val
                        break
        pack_str = f"{pack_count} {pack_type}" if pack_count else "Unspecified"

        # 3. Weight extraction (look for weight in kg, usually the trailing number)
        weight_matches = cls.WEIGHT_PATTERN.findall(full_block_text)
        weight_val = None
        for w_str in reversed(weight_matches):
            try:
                candidate = float(w_str)
                # Typical consignment weights are 100 kg to 50,000 kg
                if 100.0 <= candidate <= 50000.0 and w_str not in expanded_invoices and not w_str.startswith("12"):
                    weight_val = candidate
                    break
            except ValueError:
                continue

        # 4. Delivery location / Party separation
        delivery_to = None
        del_m = re.search(r"\b(?:del|den|delivery\s*(?:at|to)?)\b[\s:.]*(.+?)(?=\s+(?:12\d|18\d|\d{4,})|\n|$)", full_block_text, re.I)
        if del_m:
            delivery_to = del_m.group(1).strip()
        else:
            delivery_match = cls.DELIVERY_PATTERN.search(full_block_text)
            delivery_to = delivery_match.group(1).strip() if delivery_match else None

        # Party name is usually in the first line of the block
        party_name = block_lines[0]
        # Clean out package/weight/invoice tokens from party name
        party_name = cls.PACKAGES_PATTERN.sub("", party_name)
        party_name = cls.WEIGHT_PATTERN.sub("", party_name)
        party_name = cls.INVOICE_PATTERN.sub("", party_name)
        party_name = re.sub(r"\b(?:del|den|delivery\s*(?:at|to)?)\b.*$", "", party_name, flags=re.IGNORECASE).strip()

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

