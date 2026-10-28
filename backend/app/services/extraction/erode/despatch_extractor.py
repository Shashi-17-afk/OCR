import re
from typing import Optional

from backend.app.schemas.erode_extraction import ErodeDespatchRow, ErodeDespatchSheet


class ErodeDespatchExtractor:
    """Extracts structured invoice lines, weights, freights, and e-way bills from Erode Despatch Details sheets."""

    TRUCK_REGEX = re.compile(
        r"(?:lorry\s*(?:number|no)|truck\s*(?:number|no)|vehicle\s*no)[\s:]*([A-Za-z]{2}\s*\d{1,2}\s*[A-Za-z]{1,3}\s*\d{4})\b",
        re.IGNORECASE,
    )
    PLATE_REGEX = re.compile(r"\b([A-Za-z]{2}\s*\d{1,2}\s*[A-Za-z]{1,3}\s*\d{4})\b", re.IGNORECASE)
    DATE_REGEX = re.compile(
        r"\bdate[\s:]*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        re.IGNORECASE,
    )

    # Line item regex matching: Sl No (optional), 10-digit invoice, customer, destination, weight, freight, eway bill
    # Example line: 1  1250510477  LAKSHMI COTTAGE INDUSTRY  CHENNAI 1354.0  2-  2505  521945263506  c512d0d080
    ROW_REGEX = re.compile(
        r"(?:(?P<sl_no>\d{1,2})\s+)?(?P<inv_no>12\d{8})\s+(?P<cust>.+?)\s+(?P<dest>[A-Z]{3,15})\s+(?P<weight>\d+(?:\.\d+)?)\s*(?:[a-z0-9-]+\s+)?(?P<freight>\d+(?:\.\d+)?)\s+(?P<eway>\d{12})",
        re.IGNORECASE,
    )

    # Direct booking variation where destination and weight might precede 0 freight
    # Example line: 1  1250608568  SDR PRINTERS  GHAZIABAD 25251.0  0  561945196361  c4ea7c79e5
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
            # If line weights match footer total, boost confidence
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

    @classmethod
    def _extract_rows(cls, text: str) -> list[ErodeDespatchRow]:
        rows: list[ErodeDespatchRow] = []
        seen_invoices: set[str] = set()

        for line in text.splitlines():
            line_clean = line.strip()
            if not line_clean or "inv no" in line_clean.lower():
                continue

            # Try matching standard row or direct row
            match = cls.ROW_REGEX.search(line_clean) or cls.DIRECT_ROW_REGEX.search(line_clean)
            if match:
                inv_no = match.group("inv_no")
                if inv_no in seen_invoices:
                    continue
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

        return rows

    @classmethod
    def _extract_totals(cls, text: str) -> tuple[Optional[int], Optional[float], Optional[float], Optional[int]]:
        bundles = None
        gross_wt = None
        net_wt = None
        no_inv = None

        m_tot = cls.TOTAL_ROW_REGEX.search(text)
        if m_tot:
            bundles = int(m_tot.group("bund"))
            net_wt = float(m_tot.group("net"))
            gross_wt = float(m_tot.group("gross"))

        m_bund = cls.TOTALS_BUND_REGEX.search(text)
        if m_bund and bundles is None:
            bundles = int(m_bund.group(1))

        m_gross = cls.TOTALS_GROSS_REGEX.search(text)
        if m_gross and gross_wt is None:
            gross_wt = float(m_gross.group(1))

        m_net = cls.TOTALS_NET_REGEX.search(text)
        if m_net and net_wt is None:
            net_wt = float(m_net.group(1))

        m_no_inv = cls.TOTALS_NO_INV_REGEX.search(text)
        if m_no_inv:
            no_inv = int(m_no_inv.group(1))
        else:
            m_no = re.search(r"\b(?:pm\d+[-\d]*|total)\s+\d+\s+\d+\s+\d+\s+(\d+)\b", text, re.IGNORECASE)
            if m_no:
                no_inv = int(m_no.group(1))

        return bundles, gross_wt, net_wt, no_inv

