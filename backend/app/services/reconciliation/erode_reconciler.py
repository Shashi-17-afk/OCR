from typing import Optional

from backend.app.schemas.classification import BookingType, LoadingPoint
from backend.app.schemas.erode_extraction import (
    ErodeDespatchSheet,
    ErodeLRRow,
    ErodeLRSheet,
    ErodeTruckBundle,
)
from backend.app.schemas.reconciliation import (
    ConsignmentReconciliation,
    ReconciliationStatus,
    TruckReconciliationDossier,
)
from backend.app.services.grouping.erode_linker import ErodeLinkResult, ErodeLinker
from backend.app.services.reconciliation.range_compressor import InvoiceRangeCompressor


class ErodeReconciler:
    """Reconciles Erode LR sheets and Despatch Details sheets in accordance with PRD §5 and §6."""

    @classmethod
    def reconcile(
        cls,
        lr_sheet: Optional[ErodeLRSheet],
        despatch_sheet: Optional[ErodeDespatchSheet],
        booking_type: BookingType,
    ) -> TruckReconciliationDossier:
        # 1. Link Despatch invoices to LR rows
        link_res: ErodeLinkResult = ErodeLinker.link(
            lr_sheet=lr_sheet,
            despatch_sheet=despatch_sheet,
            booking_type=booking_type,
        )

        reconciled_consignments: list[ConsignmentReconciliation] = []
        truck_total_weight_kg = 0.0
        truck_total_packages = 0

        for idx, item in enumerate(link_res.consignments, start=1):
            lr = item.lr_row
            despatch_rows = item.linked_despatch_rows
            audit_notes: list[str] = []

            # A. Identification
            lr_raw = lr.lr_number.strip()
            lr_norm = lr_raw.lstrip("0") or "0"
            consignee = lr.party_name.strip()
            bill_to = consignee

            # B. Delivery destination & Party vs Delivery check (PRD §5.4, §6.1, §6.2)
            delivery_place = ""
            if lr.delivery_to:
                delivery_place = lr.delivery_to.strip()
            elif despatch_rows and despatch_rows[0].destination:
                delivery_place = despatch_rows[0].destination.strip()
            elif lr_sheet and lr_sheet.destination:
                delivery_place = lr_sheet.destination.strip()

            bill_to_differs_from_delivery = False
            if lr.delivery_to and lr.delivery_to.lower() not in consignee.lower():
                bill_to_differs_from_delivery = True
                audit_notes.append(
                    f"Bill-To differs from delivery (Delivery: {lr.delivery_to}); staff must set Bill To in TMS (PRD §5.4)."
                )

            # C. Invoices & Range Compression (PRD §5.3)
            # Combine invoices from LR row and linked despatch rows
            all_consign_invs = list(lr.invoices)
            for d in despatch_rows:
                if d.invoice_no not in all_consign_invs:
                    all_consign_invs.append(d.invoice_no)

            unique_invs = list(dict.fromkeys(all_consign_invs))
            compressed_invs = InvoiceRangeCompressor.compress(unique_invs)

            if item.unmatched_invoices:
                audit_notes.append(
                    f"LR mentions invoice(s) missing from Despatch sheet: {', '.join(item.unmatched_invoices)}"
                )

            # D. Governing Weight & Cross-check (PRD §2, §5.5)
            # Despatch gross weight wins over LR weight
            if despatch_rows:
                despatch_sum = sum(r.handwritten_weight_kg or 0.0 for r in despatch_rows)
                gov_weight_kg = round(despatch_sum if despatch_sum > 0 else (lr.weight_kg or 0.0), 2)
            else:
                gov_weight_kg = round(lr.weight_kg or 0.0, 2)

            gov_weight_mt = round(gov_weight_kg / 1000.0, 3)
            lr_weight_kg = lr.weight_kg
            weight_matches = True

            if lr_weight_kg is not None and abs(gov_weight_kg - lr_weight_kg) > 0.5:
                weight_matches = False
                diff = gov_weight_kg - lr_weight_kg
                audit_notes.append(
                    f"Despatch gross weight ({gov_weight_kg:.1f} kg) wins over LR weight ({lr_weight_kg:.1f} kg); difference: {diff:+.1f} kg (PRD §5.5)."
                )

            truck_total_weight_kg += gov_weight_kg

            # E. Packages
            total_packs = lr.package_count or 0
            if total_packs == 0 and despatch_sheet and despatch_sheet.total_bundles:
                # Fallback to total bundles from despatch
                total_packs = despatch_sheet.total_bundles // max(len(link_res.consignments), 1)
            truck_total_packages += total_packs

            # F. Freight Calculation (PRD §5.4, §6.1, §6.2)
            if despatch_rows:
                total_frt = sum(r.freight_amount for r in despatch_rows)
            else:
                total_frt = 0.0

            freight_amount = round(total_frt, 2)
            is_party_freight = (freight_amount == 0.0)

            if is_party_freight:
                audit_notes.append(
                    "Party freight (Frt Amt = 0); freight charged to dealer/consignee = 0. Staff enter Bill To manually."
                )

            # G. E-Way Bills (PRD §4 & §5.3)
            ewbs = [r.eway_bill_no for r in despatch_rows if r.eway_bill_no]
            eway_bills_cell = ", ".join(dict.fromkeys(ewbs))

            # H. Reconciliation Status
            status = ReconciliationStatus.CONFIRMED
            if bill_to_differs_from_delivery or not weight_matches or item.unmatched_invoices:
                status = ReconciliationStatus.REVIEW_REQUIRED_DISCREPANCY

            reconciled_consignments.append(
                ConsignmentReconciliation(
                    consignment_id=f"ERODE_{link_res.truck_number}_{lr_norm}",
                    source_page=lr_sheet.page_number if lr_sheet else 1,
                    lr_number_raw=lr_raw,
                    lr_number_normalized=lr_norm,
                    truck_number=link_res.truck_number,
                    booking_date=link_res.booking_date,
                    delivery_place=delivery_place,
                    consignee=consignee,
                    ship_to=delivery_place,
                    bill_to=bill_to,
                    bill_to_differs_from_ship_to=bill_to_differs_from_delivery,
                    bill_to_differs_from_delivery=bill_to_differs_from_delivery,
                    compressed_invoices_cell=compressed_invs,
                    unique_invoices=unique_invs,
                    physical_invoice_pages_count=len(despatch_rows),
                    duplicate_invoice_pages_detected=False,
                    packages_summary=lr.packages_str,
                    total_packages=total_packs,
                    governing_weight_kg=gov_weight_kg,
                    governing_weight_mt=gov_weight_mt,
                    lr_crosscheck_weight_kg=lr_weight_kg,
                    weight_matches_lr=weight_matches,
                    freight_amount=freight_amount,
                    is_party_freight=is_party_freight,
                    is_split_freight=False,
                    total_value_rs=0.0,
                    eway_bills_cell=eway_bills_cell,
                    eway_expiry_cell=None,
                    status=status,
                    audit_notes=audit_notes,
                    lr_crop_base64=lr.lr_crop_base64,
                )
            )

        # Direct booking override: if 1 consignment and despatch total gross weight exists, tie to it
        if len(reconciled_consignments) == 1 and despatch_sheet and despatch_sheet.total_gross_weight_kg:
            c = reconciled_consignments[0]
            if c.governing_weight_kg == 0.0 or abs(c.governing_weight_kg - despatch_sheet.total_gross_weight_kg) > 5.0:
                c.governing_weight_kg = round(despatch_sheet.total_gross_weight_kg, 2)
                c.governing_weight_mt = round(c.governing_weight_kg / 1000.0, 3)
            if c.total_packages == 0 and despatch_sheet.total_bundles:
                c.total_packages = despatch_sheet.total_bundles
                c.packages_summary = f"{c.total_packages} bundles"
            truck_total_weight_kg = c.governing_weight_kg
            truck_total_packages = c.total_packages

        if despatch_sheet and despatch_sheet.total_gross_weight_kg:
            truck_total_weight_kg = despatch_sheet.total_gross_weight_kg
        if despatch_sheet and despatch_sheet.total_bundles:
            truck_total_packages = despatch_sheet.total_bundles

        truck_total_weight_mt = round(truck_total_weight_kg / 1000.0, 3)
        truck_total_freight_rs = round(sum(c.freight_amount for c in reconciled_consignments), 2)
        truck_total_value_rs = round(sum(c.total_value_rs for c in reconciled_consignments), 2)
        dossier_status = ReconciliationStatus.CONFIRMED
        if any(c.status != ReconciliationStatus.CONFIRMED for c in reconciled_consignments):
            dossier_status = ReconciliationStatus.REVIEW_REQUIRED_DISCREPANCY

        return TruckReconciliationDossier(
            truck_number=link_res.truck_number,
            booking_date=link_res.booking_date,
            booking_type=booking_type,
            loading_point=LoadingPoint.ERODE,
            reconciled_consignments=reconciled_consignments,
            truck_total_weight_mt=truck_total_weight_mt,
            truck_total_packages=truck_total_packages,
            truck_total_value_rs=truck_total_value_rs,
            truck_total_freight_rs=truck_total_freight_rs,
            dossier_status=dossier_status,
        )

    @classmethod
    def reconcile_bundle(
        cls,
        bundle: ErodeTruckBundle,
    ) -> TruckReconciliationDossier:
        """Reconciles an Erode truck shipment bundle containing multiple LR and Despatch pages."""
        merged_rows: list[ErodeLRRow] = []
        dest: Optional[str] = None
        owner_name: Optional[str] = None
        owner_phone: Optional[str] = None
        driver_name: Optional[str] = None
        driver_phone: Optional[str] = None
        driver_license: Optional[str] = None

        for s in bundle.lr_sheets:
            merged_rows.extend(s.rows)
            dest = dest or s.destination
            owner_name = owner_name or s.owner_name
            owner_phone = owner_phone or s.owner_phone
            driver_name = driver_name or s.driver_name
            driver_phone = driver_phone or s.driver_phone
            driver_license = driver_license or s.driver_license

        combined_lr_sheet: Optional[ErodeLRSheet] = None
        if bundle.lr_sheets:
            first_s = bundle.lr_sheets[0]
            combined_lr_sheet = ErodeLRSheet(
                page_number=first_s.page_number,
                truck_number=bundle.truck_number,
                date=bundle.booking_date,
                destination=dest,
                owner_name=owner_name,
                owner_phone=owner_phone,
                driver_name=driver_name,
                driver_phone=driver_phone,
                driver_license=driver_license,
                rows=merged_rows,
                total_packages=sum(r.package_count or 0 for r in merged_rows) if merged_rows else None,
                total_weight_kg=sum(r.weight_kg or 0.0 for r in merged_rows) if merged_rows else None,
            )

        return cls.reconcile(
            lr_sheet=combined_lr_sheet,
            despatch_sheet=bundle.despatch_sheet,
            booking_type=bundle.booking_type,
        )
