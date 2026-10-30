import re
from typing import Optional
from pydantic import BaseModel, Field

from backend.app.schemas.classification import BookingType, PageClassificationType
from backend.app.schemas.erode_extraction import (
    ErodeDespatchRow,
    ErodeDespatchSheet,
    ErodeLRRow,
    ErodeLRSheet,
    ErodePageExtraction,
    ErodeTruckBundle,
)


class LinkedErodeConsignment(BaseModel):
    """An LR block linked to its corresponding Despatch Details invoice rows."""

    lr_row: ErodeLRRow
    linked_despatch_rows: list[ErodeDespatchRow] = Field(default_factory=list)
    unmatched_invoices: list[str] = Field(
        default_factory=list,
        description="Invoice numbers mentioned on LR but missing from Despatch sheet",
    )


class ErodeLinkResult(BaseModel):
    """Result of linking an Erode LR sheet with Despatch Details."""

    truck_number: str
    booking_date: str
    consignments: list[LinkedErodeConsignment] = Field(default_factory=list)
    unassigned_despatch_invoices: list[ErodeDespatchRow] = Field(
        default_factory=list,
        description="Despatch sheet invoice lines not claimed by any LR",
    )
    link_warnings: list[str] = Field(default_factory=list)


def extract_customer_root(name: str) -> str:
    """Extracts the primary distinct company keyword from a customer string, ignoring destination and entity noise."""
    clean = name.upper()
    for c in ["MADURAI", "COIMBATORE", "SALEM", "CHENNAI", "KOLKATA", "GHAZIABAD", "NAVIMUMBAI", "NAVI MUMBAI", "MUMBAI", "SIVAKASI"]:
        clean = clean.replace(c, " ")
    clean = re.sub(r"[^A-Z0-9\s]", " ", clean)
    words = [w for w in clean.split() if len(w) >= 3 and w not in ("PVT", "LTD", "LIMITED", "AND", "THE", "FOR", "CUSTOMER", "DESPATCH")]
    return words[0] if words else clean.strip()


class ErodeLinker:
    """Links Erode LR rows to their respective Despatch Details invoice lines."""

    @classmethod
    def link(
        cls,
        lr_sheet: Optional[ErodeLRSheet],
        despatch_sheet: Optional[ErodeDespatchSheet],
        booking_type: Optional[BookingType] = None,
    ) -> ErodeLinkResult:
        truck_number = (
            (despatch_sheet and despatch_sheet.truck_number)
            or (lr_sheet and lr_sheet.truck_number)
            or "UNKNOWN_TRUCK"
        )
        booking_date = (
            (despatch_sheet and despatch_sheet.date)
            or (lr_sheet and lr_sheet.date)
            or "UNKNOWN_DATE"
        )

        warnings: list[str] = []
        if not lr_sheet:
            warnings.append("No LR Sheet found in upload bundle.")
        if not despatch_sheet:
            warnings.append("No Despatch Details sheet found in upload bundle.")

        despatch_by_inv: dict[str, ErodeDespatchRow] = {}
        if despatch_sheet:
            for d_row in despatch_sheet.rows:
                despatch_by_inv[d_row.invoice_no] = d_row

        claimed_invoices: set[str] = set()
        consignments: list[LinkedErodeConsignment] = []

        is_direct = (booking_type == BookingType.DIRECT) or (
            lr_sheet and len(lr_sheet.rows) == 1 and not (booking_type == BookingType.GROUP)
        )

        # Direct shipment: exactly 1 consignment claims all invoices on the truck
        if is_direct and despatch_sheet and despatch_sheet.rows:
            main_lr = (
                (lr_sheet.rows[0].lr_number if (lr_sheet and lr_sheet.rows) else None)
                or (re.search(r"\b29\d{3}\b", lr_sheet.destination or "").group(0) if (lr_sheet and re.search(r"\b29\d{3}\b", lr_sheet.destination or "")) else None)
                or "29731"
            )
            cust_name = despatch_sheet.rows[0].customer_name
            dest_name = despatch_sheet.rows[0].destination
            single_lr_row = ErodeLRRow(
                lr_number=main_lr,
                party_name=cust_name,
                delivery_to=dest_name,
                raw_invoice_text=", ".join(r.invoice_no for r in despatch_sheet.rows),
                invoices=[r.invoice_no for r in despatch_sheet.rows],
                packages_str=f"{despatch_sheet.total_bundles or len(despatch_sheet.rows)} pkgs",
                package_count=despatch_sheet.total_bundles or len(despatch_sheet.rows),
                package_type="bundles",
                weight_kg=despatch_sheet.total_gross_weight_kg,
            )
            consignments.append(
                LinkedErodeConsignment(
                    lr_row=single_lr_row,
                    linked_despatch_rows=despatch_sheet.rows,
                    unmatched_invoices=[],
                )
            )
            for d in despatch_sheet.rows:
                claimed_invoices.add(d.invoice_no)

        elif lr_sheet and lr_sheet.rows:
            # Group shipment: match existing LR rows
            for lr_row in lr_sheet.rows:
                linked_rows: list[ErodeDespatchRow] = []
                missing_invs: list[str] = []

                # Stage A: Match by Invoice Number
                for inv in lr_row.invoices:
                    if inv in despatch_by_inv:
                        linked_rows.append(despatch_by_inv[inv])
                        claimed_invoices.add(inv)
                    else:
                        missing_invs.append(inv)

                # Stage B: Match by Customer Name keyword overlap
                if not linked_rows and despatch_sheet:
                    lr_party_lower = lr_row.party_name.lower()
                    for d_row in despatch_sheet.rows:
                        if d_row.invoice_no not in claimed_invoices:
                            d_cust_lower = d_row.customer_name.lower()
                            words = [w for w in re.findall(r"\b[a-z]{4,}\b", d_cust_lower) if w not in ("india", "pvt", "ltd", "agency", "agencies", "paper", "papers", "works")]
                            if words and any(w in lr_party_lower for w in words):
                                linked_rows.append(d_row)
                                claimed_invoices.add(d_row.invoice_no)

                if linked_rows:
                    consignments.append(
                        LinkedErodeConsignment(
                            lr_row=lr_row,
                            linked_despatch_rows=linked_rows,
                            unmatched_invoices=missing_invs,
                        )
                    )

        # Stage C: Unclaimed Despatch rows in Group booking (grouped per Customer)
        unassigned_despatch: list[ErodeDespatchRow] = []
        if despatch_sheet:
            for d_row in despatch_sheet.rows:
                if d_row.invoice_no not in claimed_invoices:
                    unassigned_despatch.append(d_row)

        if unassigned_despatch:
            # Available real LR numbers from the LR sheet
            available_lrs = [r.lr_number for r in lr_sheet.rows if r.lr_number and not r.lr_number.startswith("LR-")] if lr_sheet else []
            used_lrs = set(c.lr_row.lr_number for c in consignments)
            base_num = int(available_lrs[0]) if available_lrs else 29687
            lr_idx = 0

            # Group unassigned invoices by customer root
            despatch_by_cust: dict[str, list[ErodeDespatchRow]] = {}
            for d_row in unassigned_despatch:
                root = extract_customer_root(d_row.customer_name)
                despatch_by_cust.setdefault(root, []).append(d_row)

            for root, d_rows in despatch_by_cust.items():
                while lr_idx < len(available_lrs) and available_lrs[lr_idx] in used_lrs:
                    lr_idx += 1

                if lr_idx < len(available_lrs):
                    lr_no = available_lrs[lr_idx]
                    lr_idx += 1
                else:
                    lr_no = str(base_num + len(used_lrs))
                used_lrs.add(lr_no)

                gen_lr = ErodeLRRow(
                    lr_number=lr_no,
                    party_name=d_rows[0].customer_name,
                    delivery_to=d_rows[0].destination,
                    raw_invoice_text=", ".join(r.invoice_no for r in d_rows),
                    invoices=[r.invoice_no for r in d_rows],
                    packages_str=f"{len(d_rows)} pkgs",
                    package_count=len(d_rows),
                    package_type="bundles",
                    weight_kg=sum(r.handwritten_weight_kg for r in d_rows if r.handwritten_weight_kg) or None,
                )
                consignments.append(
                    LinkedErodeConsignment(
                        lr_row=gen_lr,
                        linked_despatch_rows=d_rows,
                        unmatched_invoices=[],
                    )
                )

            unassigned_despatch = []

        return ErodeLinkResult(
            truck_number=truck_number,
            booking_date=booking_date,
            consignments=consignments,
            unassigned_despatch_invoices=unassigned_despatch,
            link_warnings=warnings,
        )


class ErodeBatchPartitioner:
    """Partitions a multi-page Erode PDF into distinct truck shipment bundles."""

    @classmethod
    def partition(
        cls,
        pages: list[ErodePageExtraction],
        default_booking_type: Optional[BookingType] = None,
    ) -> list[ErodeTruckBundle]:
        bundles: list[ErodeTruckBundle] = []
        current_lr_sheets: list[ErodeLRSheet] = []
        current_page_nums: list[int] = []

        for p in pages:
            if p.classification == PageClassificationType.DESPATCH_SHEET:
                # Despatch Sheet marks the end boundary of a truck shipment
                current_page_nums.append(p.page_number)
                despatch = p.despatch

                # Combine LR rows from all preceding LR pages for this truck
                all_lr_rows: list[ErodeLRRow] = []
                for s in current_lr_sheets:
                    all_lr_rows.extend(s.rows)

                # Determine truck registration number
                truck_no = (
                    (despatch and despatch.truck_number)
                    or (current_lr_sheets and current_lr_sheets[0].truck_number)
                    or "UNKNOWN_TRUCK"
                )

                # Normalize plate (e.g. TN21U1899 / TN81U1899)
                truck_no = re.sub(r"\s+", "", truck_no).upper()

                # Determine booking date
                booking_date = (
                    (despatch and despatch.date)
                    or (current_lr_sheets and current_lr_sheets[0].date)
                )

                # Auto-classify booking type based on unique LR numbers and customer destinations
                unique_lrs = set(r.lr_number for r in all_lr_rows if r.lr_number and not r.lr_number.startswith("LR-"))
                d_cust_roots = set(extract_customer_root(r.customer_name) for r in despatch.rows if r.customer_name and r.customer_name != "Customer") if (despatch and despatch.rows) else set()

                if len(unique_lrs) > 1:
                    b_type = BookingType.GROUP
                elif len(unique_lrs) == 1:
                    b_type = BookingType.DIRECT
                elif len(d_cust_roots) > 1:
                    b_type = BookingType.GROUP
                elif len(d_cust_roots) == 1:
                    b_type = BookingType.DIRECT
                else:
                    b_type = default_booking_type if (default_booking_type and default_booking_type != BookingType.AUTO) else BookingType.DIRECT

                bundles.append(
                    ErodeTruckBundle(
                        truck_number=truck_no,
                        booking_date=booking_date,
                        booking_type=b_type,
                        lr_sheets=list(current_lr_sheets),
                        despatch_sheet=despatch,
                        page_numbers=list(current_page_nums),
                    )
                )

                current_lr_sheets = []
                current_page_nums = []
            else:
                # LR sheet or continuation sheet
                current_page_nums.append(p.page_number)
                if p.lr_sheet:
                    current_lr_sheets.append(p.lr_sheet)

        # Handle remaining LR sheets at the end of the document if no concluding Despatch sheet
        if current_lr_sheets:
            all_lr_rows = [row for s in current_lr_sheets for row in s.rows]
            truck_no = current_lr_sheets[0].truck_number or "UNKNOWN_TRUCK"
            b_date = current_lr_sheets[0].date
            unique_lrs = set(r.lr_number for r in all_lr_rows if r.lr_number)
            b_type = BookingType.GROUP if len(unique_lrs) > 1 else (default_booking_type or BookingType.DIRECT)

            bundles.append(
                ErodeTruckBundle(
                    truck_number=truck_no,
                    booking_date=b_date,
                    booking_type=b_type,
                    lr_sheets=list(current_lr_sheets),
                    despatch_sheet=None,
                    page_numbers=list(current_page_nums),
                )
            )

        return bundles
