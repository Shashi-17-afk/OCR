from typing import Optional
from pydantic import BaseModel, Field

from backend.app.schemas.erode_extraction import (
    ErodeDespatchRow,
    ErodeDespatchSheet,
    ErodeLRRow,
    ErodeLRSheet,
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


class ErodeLinker:
    """Links Erode LR rows to their respective Despatch Details invoice lines."""

    @classmethod
    def link(
        cls,
        lr_sheet: Optional[ErodeLRSheet],
        despatch_sheet: Optional[ErodeDespatchSheet],
    ) -> ErodeLinkResult:
        truck_number = (
            (lr_sheet and lr_sheet.truck_number)
            or (despatch_sheet and despatch_sheet.truck_number)
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

        despatch_by_inv = {}
        if despatch_sheet:
            for d_row in despatch_sheet.rows:
                despatch_by_inv[d_row.invoice_no] = d_row

        claimed_invoices: set[str] = set()
        consignments: list[LinkedErodeConsignment] = []

        if lr_sheet:
            for lr_row in lr_sheet.rows:
                linked_rows: list[ErodeDespatchRow] = []
                missing_invs: list[str] = []

                for inv in lr_row.invoices:
                    if inv in despatch_by_inv:
                        linked_rows.append(despatch_by_inv[inv])
                        claimed_invoices.add(inv)
                    else:
                        missing_invs.append(inv)

                consignments.append(
                    LinkedErodeConsignment(
                        lr_row=lr_row,
                        linked_despatch_rows=linked_rows,
                        unmatched_invoices=missing_invs,
                    )
                )

        unassigned_despatch: list[ErodeDespatchRow] = []
        if despatch_sheet:
            for d_row in despatch_sheet.rows:
                if d_row.invoice_no not in claimed_invoices:
                    unassigned_despatch.append(d_row)

        if unassigned_despatch:
            unassigned_nums = [d.invoice_no for d in unassigned_despatch]
            warnings.append(
                f"Despatch sheet contains {len(unassigned_despatch)} invoice(s) not claimed by any LR: {', '.join(unassigned_nums)}"
            )

        return ErodeLinkResult(
            truck_number=truck_number,
            booking_date=booking_date,
            consignments=consignments,
            unassigned_despatch_invoices=unassigned_despatch,
            link_warnings=warnings,
        )

