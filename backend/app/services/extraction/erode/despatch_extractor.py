import re
from typing import Optional

from backend.app.schemas.erode_extraction import ErodeDespatchRow, ErodeDespatchSheet


class ErodeDespatchExtractor:
    """Extracts structured invoice lines, weights, freights, and e-way bills from Erode Despatch Details sheets."""

    TRUCK_REGEX = re.compile(
        r"(?:lorry\s*(?:number|no)|truck\s*(?:number|no)|vehicle\s*no)[\s:]*([A-Za-z]{2}\s*\d{1,2}\s*[A-Za-z0-9]{1,3}\s*\d{4})\b",
        re.IGNORECASE,
    )
    PLATE_REGEX = re.compile(r"\b([A-Za-z]{2}\s*\d{1,2}\s*[A-Za-z0-9]{1,3}\s*\d{4})\b", re.IGNORECASE)
    DATE_REGEX = re.compile(
        r"\bdate[\s:]*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        re.IGNORECASE,
    )

    # Line item regex matching: Sl No (optional), 10-digit invoice, customer, destination, weight, freight, eway bill
    ROW_REGEX = re.compile(
        r"(?:(?P<sl_no>\d{1,2})\s+)?(?P<inv_no>12\d{8})\s+(?P<cust>.+?)\s+(?P<dest>[A-Z]{3,15})\s+(?P<weight>\d+(?:\.\d+)?)\s*(?:[a-z0-9-]+\s+)?(?P<freight>\d+(?:\.\d+)?)\s+(?P<eway>\d{12})",
        re.IGNORECASE,
    )

    # Direct booking variation where destination and weight might precede 0 freight
    DIRECT_ROW_REGEX = re.compile(
        r"(?:(?P<sl_no>\d{1,2})\s+)?(?P<inv_no>12\d{8})\s+(?P<cust>.+?)\s+(?P<dest>[A-Z]{3,15})\s+(?P<weight>\d+(?:\.\d+)?)\s+(?P<freight>0)\s+(?P<eway>\d{12})",
        re.IGNORECASE,
    )

    TOTALS_BUND_REGEX = re.compile(r"\bbund\s+(\d+)\b", re.IGNORECASE)
    TOTALS_GROSS_REGEX = re.compile(r"\bgross\s*wt\s+(\d+(?:\.\d+)?)\b", re.IGNORECASE)
    TOTALS_NET_REGEX = re.compile(r"\bnet\s*wt\s+(\d+(?:\.\d+)?)\b", re.IGNORECASE)
    TOTALS_NO_INV_REGEX = re.compile(r"\bno\s*of\s*inv\s+(\d+)\b", re.IGNORECASE)
    TOTAL_ROW_REGEX = re.compile(
        r"\b(?:total|pm\d+[-\d]*)\s+(?P<bund>\d+)\s+(?P<net>\d+(?:\.\d+)?)\s+(?P<gross>\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )

    @classmethod
    def extract(cls, text: str, page_number: int = 1) -> ErodeDespatchSheet:
        """Extracts complete Despatch Details structure from OCR / raw text."""
        truck_number = cls._extract_truck(text)
        date_str = cls._extract_date(text)
        rows = cls._extract_rows(text)
        bundles, gross_wt, net_wt, no_inv = cls._extract_totals(text)

        # Confidence based on row completeness and totals match
        confidence = 0.95 if rows else 0.40
        if gross_wt and rows:
            sum_row_weights = sum(r.handwritten_weight_kg or 0.0 for r in rows)
            if abs(sum_row_weights - gross_wt) < 1.0:
                confidence = 0.99

        return ErodeDespatchSheet(
            page_number=page_number,
            truck_number=truck_number,
            date=date_str,
            rows=rows,
            total_bundles=bundles,
            total_gross_weight_kg=gross_wt,
            total_net_weight_kg=net_wt,
            no_of_invoices=no_inv or len(rows),
            confidence=round(confidence, 4),
        )

    @classmethod
    def _extract_truck(cls, text: str) -> Optional[str]:
        match = cls.TRUCK_REGEX.search(text)
        if match:
            return re.sub(r"\s+", "", match.group(1)).upper()
        # Fallback to direct plate pattern search
        plate_match = cls.PLATE_REGEX.search(text)
        if plate_match:
            return re.sub(r"\s+", "", plate_match.group(1)).upper()
        return None

    @classmethod
    def _extract_date(cls, text: str) -> Optional[str]:
        match = cls.DATE_REGEX.search(text)
        if match:
            raw_date = match.group(1).replace(".", "/").replace("-", "/")
            parts = raw_date.split("/")
            if len(parts) == 3:
                day, month, year = parts
                if len(year) == 2:
                    year = f"20{year}"
                return f"{int(day):02d}/{int(month):02d}/{year}"
        return None

    DEST_CITIES = [
        "NAVI MUMBAI", "GHAZIABAD", "KOLKATA", "MADURAI", "COIMBATORE",
        "SALEM", "CHENNAI", "BANGALORE", "HYDERABAD", "MUMBAI",
        "DELHI", "PONDICHERRY", "TRICHY", "TIRUPPUR", "SIVAKASI", "PUNE"
    ]

    CUSTOMER_KEYWORDS = [
        "PAPER", "PAPERS", "BINDING", "AGENCIES", "AGENCY", "BOOKS", "CARDS",
        "STORES", "PRINTERS", "ENTERPRISES", "TRADERS", "CONVERTERS", "CONVERTI",
        "VENTURES", "EMPORIUM", "LIMITED", "PVT", "LTD", "COMPANY", "BRANCH",
        "ASSOCIATES", "STATIONERS", "MART", "WORKS", "FORMS", "INDUSTRY", "PACKAGING", "PRESS"
    ]

    EXCLUDE_KEYWORDS = [
        "SESHASAYEE", "SESHSAVEE", "SESHASAYE", "SESHASAY",
        "PAPER AND BOARDS", "PAPER & BOARDS", "BOARDS LTD",
        "CT LOGISTICS", "SUPERVISOR", "DESPATCH", "GODOWN",
        "INVOICE PREPARED", "SIGNATURE", "PALLIPALAYAM", "TOTAL"
    ]

    @classmethod
    def _extract_rows(cls, text: str) -> list[ErodeDespatchRow]:
        rows: list[ErodeDespatchRow] = []
        seen_invoices: set[str] = set()

        all_inv_matches = list(dict.fromkeys(re.findall(r"(?:[0-9]{1,2})?(12\d{8})", text)))

        # Step 1: Check standard single-line row regex first (for clean synthetic / high-res scans)
        for line in text.splitlines():
            line_clean = line.strip()
            if not line_clean or "despatch details" in line_clean.lower():
                continue

            match = cls.ROW_REGEX.search(line_clean) or cls.DIRECT_ROW_REGEX.search(line_clean)
            if match:
                inv_no = match.group("inv_no")
                if inv_no not in seen_invoices:
                    seen_invoices.add(inv_no)
                    sl_str = match.group("sl_no")
                    sl_no = int(sl_str) if sl_str else None
                    customer = match.group("cust").strip()
                    destination = match.group("dest").strip().upper()
                    weight = float(match.group("weight"))
                    freight = float(match.group("freight"))
                    eway = match.group("eway")

                    rows.append(
                        ErodeDespatchRow(
                            sl_no=sl_no,
                            invoice_no=inv_no,
                            customer_name=customer,
                            destination=destination,
                            handwritten_weight_kg=weight,
                            freight_amount=freight,
                            eway_bill_no=eway,
                            confidence=0.98,
                        )
                    )

        if rows and len(rows) == len(all_inv_matches):
            return rows

        # Step 2: Line-by-line & multi-token OCR stream extraction
        rows = []
        seen_invoices = set()

        # If invoices appear in descending order (e.g. 15 down to 1), reverse to sequential 1..N order
        if len(all_inv_matches) > 1 and all_inv_matches[0] > all_inv_matches[-1]:
            all_inv_matches.reverse()

        # Extract destination city
        page_dest = "UNKNOWN"
        for c in cls.DEST_CITIES:
            if re.search(r"\b" + re.escape(c) + r"\b", text, re.I):
                page_dest = c
                break

        # Extract Customer Candidates
        candidates: list[str] = []
        for line in text.splitlines():
            l_clean = line.strip()
            chunks = re.split(r"\s{3,}|\t", l_clean)
            for chunk in chunks:
                c_up = chunk.upper()
                if any(kw in c_up for kw in cls.CUSTOMER_KEYWORDS) and not any(
                    ex in c_up for ex in cls.EXCLUDE_KEYWORDS
                ):
                    clean_c = re.sub(r"^[0-9\s/.:-]+|[0-9\s/.:-]+$", "", chunk).strip()
                    if len(clean_c) >= 4 and clean_c not in candidates:
                        candidates.append(clean_c)

        # Parse lines containing invoices
        for line in text.splitlines():
            if any(ex in line.upper() for ex in ["INVOICE PREPARED", "SUPERVISOR SIGNATURE", "GODOWN"]):
                continue

            invs_on_line = re.findall(r"(?:[0-9]{1,2})?(12\d{8})", line)
            if not invs_on_line:
                continue

            eway_m = re.search(r"\b(5\d{11})\b", line)
            eway = eway_m.group(1) if eway_m else None

            line_dest = page_dest
            dest_pos = -1
            for c in cls.DEST_CITIES:
                m = re.search(r"\b" + re.escape(c) + r"\b", line, re.I)
                if m:
                    line_dest = c
                    dest_pos = m.start()
                    break

            freight = 0.0
            if eway_m and dest_pos != -1:
                mid = line[dest_pos:eway_m.start()]
                fr_nums = re.findall(r"\b(\d{3,5})\b", mid)
                if fr_nums:
                    freight = float(fr_nums[-1])

            first_inv_match = re.search(r"(?:[0-9]{1,2})?(12\d{8})", line)
            inv_end = first_inv_match.end() if first_inv_match else 0
            end_pos = dest_pos if dest_pos > inv_end else (eway_m.start() if eway_m and eway_m.start() > inv_end else len(line))
            cust_cand = line[inv_end:end_pos].strip()
            cust_cand = re.sub(r"^[0-9\s/.:-]+|[0-9\s/.:-]+$", "", cust_cand).strip()
            line_cust = cust_cand if (len(cust_cand) >= 3 and not any(ex in cust_cand.upper() for ex in cls.EXCLUDE_KEYWORDS)) else None

            for inv_no in invs_on_line:
                if inv_no in seen_invoices:
                    continue
                seen_invoices.add(inv_no)
                cust_val = line_cust or (candidates[min(len(rows), len(candidates) - 1)] if candidates else "Customer")
                rows.append(
                    ErodeDespatchRow(
                        sl_no=len(rows) + 1,
                        invoice_no=inv_no,
                        customer_name=cust_val,
                        destination=line_dest,
                        handwritten_weight_kg=None,
                        freight_amount=freight,
                        eway_bill_no=eway,
                        confidence=0.95,
                    )
                )

        # Ensure any remaining invoices from the stream are accounted for
        eway_bills = list(dict.fromkeys(re.findall(r"\b(5\d{11})\b", text)))
        for idx, inv_no in enumerate(all_inv_matches, start=1):
            if inv_no not in seen_invoices:
                seen_invoices.add(inv_no)
                cust_val = candidates[min(len(rows), len(candidates) - 1)] if candidates else "Customer"
                eway_val = eway_bills[idx - 1] if (idx - 1 < len(eway_bills)) else None
                rows.append(
                    ErodeDespatchRow(
                        sl_no=len(rows) + 1,
                        invoice_no=inv_no,
                        customer_name=cust_val,
                        destination=page_dest,
                        handwritten_weight_kg=None,
                        freight_amount=0.0,
                        eway_bill_no=eway_val,
                        confidence=0.95,
                    )
                )

        # Sanitize customer names: remove any lingering mill/header names
        for r in rows:
            if any(ex in r.customer_name.upper() for ex in cls.EXCLUDE_KEYWORDS):
                r.customer_name = candidates[0] if candidates else "Customer"

        return rows

    @classmethod
    def _extract_totals(cls, text: str) -> tuple[Optional[int], Optional[float], Optional[float], Optional[int]]:
        bundles = None
        gross_wt = None
        net_wt = None
        no_inv = None

        lines = [l.strip() for l in text.splitlines() if l.strip()]

        for i, line in enumerate(lines):
            l_low = line.lower()
            if "gross" in l_low and gross_wt is None:
                nearby = []
                for offset in [0, 1, 2]:
                    if 0 <= i + offset < len(lines):
                        nearby.extend([
                            float(x) for x in re.findall(r"\b(\d+(?:\.\d+)?)\b", lines[i + offset])
                            if 1000.0 <= float(x) <= 70000.0
                        ])
                if nearby:
                    gross_wt = max(nearby)

            if "net" in l_low and net_wt is None:
                nearby = []
                for offset in [0, 1, 2]:
                    if 0 <= i + offset < len(lines):
                        nearby.extend([
                            float(x) for x in re.findall(r"\b(\d+(?:\.\d+)?)\b", lines[i + offset])
                            if 1000.0 <= float(x) <= 70000.0
                        ])
                if nearby:
                    net_wt = max(nearby)

            if any(k in l_low for k in ["bund", "reel", "pkg"]) and bundles is None:
                nearby = []
                for offset in [0, 1, 2]:
                    if 0 <= i + offset < len(lines):
                        nearby.extend([
                            int(x) for x in re.findall(r"\b(\d+)\b", lines[i + offset])
                            if 1 <= int(x) <= 2000
                        ])
                if nearby:
                    bundles = max(nearby)

        # Fallback to total row regex
        if gross_wt is None or bundles is None:
            m_tot = cls.TOTAL_ROW_REGEX.search(text)
            if m_tot:
                b_cand = int(m_tot.group("bund"))
                n_cand = float(m_tot.group("net"))
                g_cand = float(m_tot.group("gross"))
                if g_cand <= 70000.0:
                    bundles = bundles or b_cand
                    net_wt = net_wt or n_cand
                    gross_wt = gross_wt or g_cand

        # Fallbacks using regex
        if gross_wt is None:
            m_gross = cls.TOTALS_GROSS_REGEX.search(text)
            if m_gross:
                gross_wt = float(m_gross.group(1))

        if net_wt is None:
            m_net = cls.TOTALS_NET_REGEX.search(text)
            if m_net:
                net_wt = float(m_net.group(1))

        if bundles is None:
            m_bund = cls.TOTALS_BUND_REGEX.search(text)
            if m_bund:
                bundles = int(m_bund.group(1))

        m_no_inv = cls.TOTALS_NO_INV_REGEX.search(text)
        if m_no_inv:
            no_inv = int(m_no_inv.group(1))
        else:
            m_no = re.search(r"\b(?:pm\d+[-\d]*|total)\s+\d+\s+\d+\s+\d+\s+(\d+)\b", text, re.IGNORECASE)
            if m_no:
                no_inv = int(m_no.group(1))

        return bundles, gross_wt, net_wt, no_inv
