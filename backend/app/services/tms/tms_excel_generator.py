"""
TMS Excel Exporter for BeSpoke Logistics Extraction Engine.
Generates completed, formatted .xlsx workbooks strictly matching the client's TMS format:
- CTLS TMS Booking Fields.xlsx
Supports Direct Booking (28 columns) and Group Booking (72 columns),
repeating trip/shipper details per consignment/LR row as specified by the client.
"""

import io
import os
from pathlib import Path
from typing import Any, Optional
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from backend.app.core.logging import logger
from backend.app.schemas.classification import BookingType
from backend.app.schemas.tms_booking import (
    FieldStatus,
    TMSReviewResponse,
    TMSTruckDossier,
)
from backend.app.services.tms.tms_mapper import (
    DIRECT_BOOKING_COLUMNS,
    GROUP_BOOKING_COLUMNS,
    to_clean_id,
)

# Template file path
TEMPLATE_PATH = Path(r"D:\BeSpoke\TEST-m\CTLS TMS Booking Fields.xlsx")


class TMSExcelExporter:
    """Exports completed TMS Booking dossiers into the client's official Excel format."""

    @classmethod
    def export(
        cls,
        review: TMSReviewResponse,
        template_path: Optional[Path] = None,
    ) -> bytes:
        """
        Populates and exports the TMS Excel workbook from a TMSReviewResponse.
        Returns the raw .xlsx bytes for streaming to user or saving.
        """
        tpl_path = template_path or TEMPLATE_PATH
        if tpl_path.exists():
            wb = openpyxl.load_workbook(str(tpl_path))
        else:
            wb = cls._create_fallback_workbook()

        # Populate Direct Booking
        if "Direct Booking" in wb.sheetnames:
            ws_direct = wb["Direct Booking"]
            cls._populate_direct_booking(ws_direct, review.trucks)

        # Populate Group Booking
        if "Group Booking" in wb.sheetnames:
            ws_group = wb["Group Booking"]
            cls._populate_group_booking(ws_group, review.trucks)

        output_stream = io.BytesIO()
        wb.save(output_stream)
        output_stream.seek(0)
        return output_stream.getvalue()

    @staticmethod
    def _to_float(val: Any) -> Optional[float]:
        """Safely parses float from numeric or string values."""
        if val is None or val == "":
            return None
        if isinstance(val, (int, float)):
            return float(val)
        try:
            return float(str(val).replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _to_int(val: Any) -> Optional[int]:
        """Safely parses int from numeric or string values."""
        if val is None or val == "":
            return None
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val)
        try:
            return int(float(str(val).replace(",", "").strip()))
        except (ValueError, TypeError):
            return None

    @classmethod
    def _get_truck_total_freight(cls, truck: TMSTruckDossier) -> Optional[float]:
        """Calculates total customer freight for truck: sum of consignment freights, or truck total freight."""
        consignment_freights = []
        for c in (truck.consignments or []):
            val = cls._get_field_val(truck, c, "freight_charges", None)
            if val is not None and isinstance(val, (int, float)) and val > 0:
                consignment_freights.append(float(val))
        if consignment_freights:
            return round(sum(consignment_freights), 2)
        if truck.total_freight_rs and truck.total_freight_rs > 0:
            return round(float(truck.total_freight_rs), 2)
        val = cls._get_field_val(truck, None, "customer_freight_charges", None)
        if val is not None and isinstance(val, (int, float)) and val > 0:
            return round(float(val), 2)
        return None

    @classmethod
    def _get_vendor_freight(cls, truck: TMSTruckDossier) -> Optional[float]:
        """Retrieves vendor freight if explicitly provided; otherwise None (blank for Phase 2)."""
        val = cls._get_field_val(truck, None, "vendor_freight_charges", None)
        if val is not None and isinstance(val, (int, float)) and val > 0:
            return round(float(val), 2)
        return None

    @classmethod
    def _populate_direct_booking(
        cls,
        ws: openpyxl.worksheet.worksheet.Worksheet,
        trucks: list[TMSTruckDossier],
    ) -> None:
        """
        Populates 'Direct Booking' sheet:
        One row per truck booking starting at row 6.
        """
        start_row = 6
        thin_border = Border(
            left=Side(style="thin", color="D3D3D3"),
            right=Side(style="thin", color="D3D3D3"),
            top=Side(style="thin", color="D3D3D3"),
            bottom=Side(style="thin", color="D3D3D3"),
        )
        data_font = Font(name="Calibri", size=10)

        current_row = start_row
        for truck in trucks:
            # Map fields for Direct Booking
            first_c = truck.consignments[0] if truck.consignments else None
            first_inv = first_c.invoice_records[0] if (first_c and first_c.invoice_records) else None

            # Values mapping by column index (1-based)
            row_vals: dict[int, Any] = {
                1: cls._get_field_val(truck, None, "booking_branch", ""),
                2: cls._get_field_val(truck, None, "bill_from", ""),
                3: cls._get_field_val(truck, None, "shipper", "Seshasayee Paper and Boards Limited"),
                4: cls._get_field_val(truck, None, "bill_to", ""),
                5: cls._get_field_val(truck, None, "vehicle_type", "Open Body / Tarpaulin"),
                6: cls._get_field_val(truck, None, "pickup_date", truck.booking_date),
                7: truck.total_gross_weight_mt if truck.total_gross_weight_mt > 0 else cls._get_field_val(truck, first_c, "weight", ""),
                8: truck.total_packages if truck.total_packages > 0 else cls._get_field_val(truck, first_c, "no_of_packs", ""),
                9: cls._get_field_val(truck, None, "cargo_type", "Paper Reels / Bundles"),
                10: cls._get_field_val(truck, None, "loading_points", "Cheranmahadevi / Tirunelveli"),
                11: cls._get_field_val(truck, first_c, "unloading_points", cls._get_field_val(truck, first_c, "party_dropdown", "")),
                12: (first_inv.eway_bill if (first_inv and first_inv.eway_bill) else cls._get_field_val(truck, first_c, "eway_bill", "")),
                13: cls._get_field_val(truck, first_c, "eway_expiry", ""),
                14: cls._get_field_val(truck, first_c, "lr_number", first_c.lr_number if first_c else ""),
                15: (first_inv.invoice_no if (first_inv and first_inv.invoice_no) else cls._get_field_val(truck, first_c, "invoice_no", "")),
                16: (first_inv.invoice_value if (first_inv and first_inv.invoice_value is not None) else cls._get_field_val(truck, first_c, "invoice_value", "")),
                17: (first_inv.invoice_date if (first_inv and first_inv.invoice_date) else cls._get_field_val(truck, first_c, "invoice_date", "")),
                18: cls._get_field_val(truck, None, "license_plate", truck.truck_number),
                19: cls._get_field_val(truck, None, "driver_name", ""),
                20: cls._get_field_val(truck, None, "driver_phone", ""),
                21: cls._get_field_val(truck, None, "vendor_name", ""),
                22: cls._get_field_val(truck, None, "account_number", ""),
                23: cls._get_field_val(truck, None, "account_name", ""),
                24: cls._get_field_val(truck, None, "bank_name", ""),
                25: cls._get_field_val(truck, None, "ifsc_code", ""),
                26: cls._get_field_val(truck, None, "pan_number", ""),
                # Column 27: total customer freight (sum of LR freight, or truck total). Blank if none.
                27: cls._get_truck_total_freight(truck),
                # Column 28: vendor freight – left blank when not provided.
                28: cls._get_vendor_freight(truck),
            }

            for col_idx in range(1, 29):
                cell = ws.cell(row=current_row, column=col_idx)
                val = row_vals.get(col_idx)

                # Format appropriately
                if col_idx == 7:
                    f_val = cls._to_float(val)
                    if f_val is not None and f_val > 0:
                        cell.value = f_val
                        cell.number_format = "#,##0.000"
                    else:
                        cell.value = ""
                elif col_idx == 8:
                    i_val = cls._to_int(val)
                    if i_val is not None and i_val > 0:
                        cell.value = i_val
                        cell.number_format = "#,##0"
                    else:
                        cell.value = ""
                elif col_idx == 16:
                    f_val = cls._to_float(val)
                    if f_val is not None and f_val > 0:
                        cell.value = f_val
                        cell.number_format = "#,##0.00"
                    else:
                        cell.value = ""
                elif col_idx == 27:
                    f_val = cls._to_float(val)
                    if f_val is not None:
                        cell.value = f_val
                        cell.number_format = "#,##0.00"
                    else:
                        cell.value = ""
                elif col_idx == 28:
                    f_val = cls._to_float(val)
                    if f_val is not None:
                        cell.value = f_val
                        cell.number_format = "#,##0.00"
                    else:
                        cell.value = ""
                elif col_idx in (12, 14, 15, 18, 20, 22, 25, 26):
                    # Ensure identifiers with potential leading zeros are strings
                    cell.value = str(val) if val is not None and val != "" else ""
                    cell.number_format = "@"
                else:
                    cell.value = val if val is not None else ""

                cell.font = data_font
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")

            current_row += 1

    @classmethod
    def _populate_group_booking(
        cls,
        ws: openpyxl.worksheet.worksheet.Worksheet,
        trucks: list[TMSTruckDossier],
    ) -> None:
        """
        Populates 'Group Booking' sheet:
        One row per LR (consignment).
        Booking, shipper, and trip details repeat on every row of the same truck.
        Starting at row 6.
        """
        start_row = 6
        thin_border = Border(
            left=Side(style="thin", color="D3D3D3"),
            right=Side(style="thin", color="D3D3D3"),
            top=Side(style="thin", color="D3D3D3"),
            bottom=Side(style="thin", color="D3D3D3"),
        )
        data_font = Font(name="Calibri", size=10)

        current_row = start_row
        for truck in trucks:
            consignments = truck.consignments or []
            if not consignments:
                # If no consignments, create at least one dummy line
                consignments = [None]

            for c_item in consignments:
                r = current_row

                # Step 1: Booking (entered once) - cols 1-7
                c1_branch = cls._get_field_val(truck, None, "booking_branch", "")
                c2_bill_from = cls._get_field_val(truck, None, "bill_from", "")
                c3_order_group = cls._get_field_val(truck, None, "order_group_ftl", "FTL")
                c4_order_type = cls._get_field_val(truck, None, "order_type_full_truck", "Full Truck")
                c5_tx_type = cls._get_field_val(truck, None, "transaction_type", "Standard")
                c6_pickup_date = cls._get_field_val(truck, None, "pickup_date", truck.booking_date)
                c7_insurance_type = cls._get_field_val(truck, None, "insurance_type", "Owner Risk")

                # Step 1: Shipper block - cols 8-21
                c8_shipper = cls._get_field_val(truck, None, "shipper", "Seshasayee Paper and Boards Limited")
                c9_bill_to = cls._get_field_val(truck, None, "bill_to", "")
                c10_gstn = cls._get_field_val(truck, None, "branch_gstn", "")
                c11_service = cls._get_field_val(truck, None, "service_type", "")
                c12_packs_trip = truck.total_packages if truck.total_packages > 0 else cls._get_field_val(truck, c_item, "no_of_packs", "")
                c13_wt_trip = truck.total_gross_weight_mt if truck.total_gross_weight_mt > 0 else cls._get_field_val(truck, c_item, "weight", "")
                c14_unit = "MT"
                c15_vol = cls._get_field_val(truck, None, "cubic_vol", "")
                c16_cargo = cls._get_field_val(truck, None, "cargo_type", "Paper Reels / Bundles")
                c17_load_point = cls._get_field_val(truck, None, "loading_points", "Cheranmahadevi / Tirunelveli")
                c18_unload_point = cls._get_field_val(truck, c_item, "unloading_points", cls._get_field_val(truck, c_item, "party_dropdown", ""))
                c19_veh_type = cls._get_field_val(truck, None, "vehicle_type", "Open Body / Tarpaulin")
                c20_del_on = cls._get_field_val(truck, None, "delivery_on", "")
                c21_pod_on = cls._get_field_val(truck, None, "pod_on", "")

                # Step 2: Trip detail - cols 22-30
                c22_vendor_type = cls._get_field_val(truck, None, "vendor_type", "Market")
                c23_plate = truck.truck_number
                c24_driver_name = cls._get_field_val(truck, None, "driver_name", "")
                c25_driver_phone = cls._get_field_val(truck, None, "driver_phone", "")
                c26_license = cls._get_field_val(truck, None, "driver_license", "")
                c27_dob = cls._get_field_val(truck, None, "driver_dob", "")
                c28_ins_co = cls._get_field_val(truck, None, "insurance_company", "")
                c29_ins_ref = cls._get_field_val(truck, None, "insurance_reference", "")
                c30_gps = cls._get_field_val(truck, None, "gps_provider", "")

                # Step 2: Consignment block (one row per LR) - cols 31-46
                first_inv = c_item.invoice_records[0] if (c_item and c_item.invoice_records) else None
                c31_code = c_item.consignment_code if c_item else "1A"
                c32_ship_drop = c8_shipper
                c33_party = cls._get_field_val(truck, c_item, "party_dropdown", cls._get_field_val(truck, c_item, "unloading_points", ""))
                c34_packs = cls._get_field_val(truck, c_item, "no_of_packs", "")
                c35_wt = cls._get_field_val(truck, c_item, "weight", "")
                c36_unit_c = "MT"
                c37_vol_c = cls._get_field_val(truck, c_item, "volume", "")
                c38_lr = cls._get_field_val(truck, c_item, "lr_number", c_item.lr_number if c_item else "")
                c39_lr_rem = cls._get_field_val(truck, c_item, "lr_remarks", "")
                c40_eway = (first_inv.eway_bill if (first_inv and first_inv.eway_bill) else cls._get_field_val(truck, c_item, "eway_bill", ""))
                c41_expiry = cls._get_field_val(truck, c_item, "eway_expiry", "")
                c42_desc = cls._get_field_val(truck, c_item, "description_cargo_type", "Paper Reels / Bundles")
                c43_inv = (first_inv.invoice_no if (first_inv and first_inv.invoice_no) else cls._get_field_val(truck, c_item, "invoice_no", ""))
                c44_inv_val = (first_inv.invoice_value if (first_inv and first_inv.invoice_value is not None) else cls._get_field_val(truck, c_item, "invoice_value", ""))
                c45_inv_dt = (first_inv.invoice_date if (first_inv and first_inv.invoice_date) else cls._get_field_val(truck, c_item, "invoice_date", ""))
                c46_c_freight = cls._get_field_val(truck, c_item, "freight_charges", "")

                # Step 3: Vendor / Pricing - cols 47-72
                c47_vendor = cls._get_field_val(truck, None, "vendor_name", "")
                c48_vcode = cls._get_field_val(truck, None, "vendor_code", "")
                c49_acct = cls._get_field_val(truck, None, "account_number", "")
                c50_aname = cls._get_field_val(truck, None, "account_name", "")
                c51_bname = cls._get_field_val(truck, None, "bank_name", "")
                c52_ifsc = cls._get_field_val(truck, None, "ifsc_code", "")
                c53_pan = cls._get_field_val(truck, None, "pan_number", "")
                c54_powo = cls._get_field_val(truck, None, "po_wo_number", "")
                c55_basis = cls._get_field_val(truck, None, "billing_basis", "")
                c56_adv_pct = cls._get_field_val(truck, None, "advance_pct", 0.0)
                c57_upload = cls._get_field_val(truck, None, "upload_file_type", "")
                c58_cust_freight = cls._get_truck_total_freight(truck)
                c59_cust_load = cls._get_field_val(truck, None, "customer_loading_charges", 0.0)
                c60_cust_unload = cls._get_field_val(truck, None, "customer_unloading_charges", 0.0)
                c61_cust_det = cls._get_field_val(truck, None, "customer_detention_charges", 0.0)
                c62_cust_misc = cls._get_field_val(truck, None, "customer_misc_charges", 0.0)
                # 63: Customer Total Charges (auto) -> formula
                c63_cust_tot_formula = f"=SUM(BF{r}:BJ{r})"

                c64_vend_freight = cls._get_vendor_freight(truck)
                c65_vend_load = cls._get_field_val(truck, None, "vendor_loading_charges", 0.0)
                c66_vend_unload = cls._get_field_val(truck, None, "vendor_unloading_charges", 0.0)
                c67_vend_det = cls._get_field_val(truck, None, "vendor_detention_charges", 0.0)
                c68_vend_misc = cls._get_field_val(truck, None, "vendor_misc_charges", 0.0)
                # 69: Vendor Total Charges (auto) -> formula
                c69_vend_tot_formula = f"=SUM(BL{r}:BP{r})"

                # 70: Margin % (auto) -> =IF(BK{r}>0, (BK{r}-BQ{r})/BK{r}*100, 0)
                c70_margin_pct_formula = f'=IF(BK{r}>0, (BK{r}-BQ{r})/BK{r}*100, 0)'
                # 71: Margin Value (auto) -> =BK{r}-BQ{r}
                c71_margin_val_formula = f"=BK{r}-BQ{r}"
                # 72: Advance Value (auto) -> =BQ{r}*(BD{r}/100)
                c72_adv_val_formula = f"=BQ{r}*(BD{r}/100)"

                # Map all 72 columns
                row_map: dict[int, Any] = {
                    1: c1_branch, 2: c2_bill_from, 3: c3_order_group, 4: c4_order_type,
                    5: c5_tx_type, 6: c6_pickup_date, 7: c7_insurance_type, 8: c8_shipper,
                    9: c9_bill_to, 10: c10_gstn, 11: c11_service, 12: c12_packs_trip,
                    13: c13_wt_trip, 14: c14_unit, 15: c15_vol, 16: c16_cargo,
                    17: c17_load_point, 18: c18_unload_point, 19: c19_veh_type,
                    20: c20_del_on, 21: c21_pod_on, 22: c22_vendor_type, 23: c23_plate,
                    24: c24_driver_name, 25: c25_driver_phone, 26: c26_license, 27: c27_dob,
                    28: c28_ins_co, 29: c29_ins_ref, 30: c30_gps, 31: c31_code,
                    32: c32_ship_drop, 33: c33_party, 34: c34_packs, 35: c35_wt,
                    36: c36_unit_c, 37: c37_vol_c, 38: c38_lr, 39: c39_lr_rem,
                    40: c40_eway, 41: c41_expiry, 42: c42_desc, 43: c43_inv,
                    44: c44_inv_val, 45: c45_inv_dt, 46: c46_c_freight, 47: c47_vendor,
                    48: c48_vcode, 49: c49_acct, 50: c50_aname, 51: c51_bname,
                    52: c52_ifsc, 53: c53_pan, 54: c54_powo, 55: c55_basis,
                    56: c56_adv_pct, 57: c57_upload, 58: c58_cust_freight, 59: c59_cust_load,
                    60: c60_cust_unload, 61: c61_cust_det, 62: c62_cust_misc,
                    63: c63_cust_tot_formula, 64: c64_vend_freight, 65: c65_vend_load,
                    66: c66_vend_unload, 67: c67_vend_det, 68: c68_vend_misc,
                    69: c69_vend_tot_formula, 70: c70_margin_pct_formula,
                    71: c71_margin_val_formula, 72: c72_adv_val_formula,
                }

                for col_idx in range(1, 73):
                    cell = ws.cell(row=current_row, column=col_idx)
                    val = row_map.get(col_idx)

                    # Handle formulas
                    if col_idx in (63, 69, 70, 71, 72):
                        cell.value = str(val)
                        cell.number_format = "#,##0.00" if col_idx != 70 else "0.00%"
                    elif col_idx in (13, 35):
                        f_val = cls._to_float(val)
                        if f_val is not None and f_val > 0:
                            cell.value = f_val
                            cell.number_format = "#,##0.000"
                        else:
                            cell.value = ""
                    elif col_idx in (12, 34):
                        i_val = cls._to_int(val)
                        if i_val is not None and i_val > 0:
                            cell.value = i_val
                            cell.number_format = "#,##0"
                        else:
                            cell.value = ""
                    elif col_idx == 44:
                        f_val = cls._to_float(val)
                        if f_val is not None and f_val > 0:
                            cell.value = f_val
                            cell.number_format = "#,##0.00"
                        else:
                            cell.value = ""
                    elif col_idx in (46, 58):
                        f_val = cls._to_float(val)
                        if f_val is not None:
                            cell.value = f_val
                            cell.number_format = "#,##0.00"
                        else:
                            cell.value = ""
                    elif col_idx in (56, 59, 60, 61, 62, 64, 65, 66, 67, 68):
                        f_val = cls._to_float(val)
                        if f_val is not None:
                            cell.value = f_val
                            cell.number_format = "#,##0.00"
                        else:
                            cell.value = ""
                    elif col_idx in (23, 25, 26, 38, 40, 43, 49, 52, 53):
                        # Leading zero preservation
                        cell.value = str(val) if val is not None and val != "" else ""
                        cell.number_format = "@"
                    else:
                        cell.value = val if val is not None else ""

                    cell.font = data_font
                    cell.border = thin_border
                    cell.alignment = Alignment(vertical="center")

                current_row += 1

    @staticmethod
    def _get_field_val(
        truck: TMSTruckDossier,
        consignment: Optional[Any],
        clean_id: str,
        default_val: Any = "",
    ) -> Any:
        """Retrieves field value from consignment or trip dictionary, falling back to default."""
        if consignment and hasattr(consignment, "fields"):
            field = consignment.fields.get(clean_id)
            if field and field.value is not None and str(field.value).strip() != "":
                return field.value

        trip_field = truck.trip_fields.get(clean_id)
        if trip_field and trip_field.value is not None and str(trip_field.value).strip() != "":
            return trip_field.value

        return default_val

    @classmethod
    def _create_fallback_workbook(cls) -> openpyxl.Workbook:
        """Creates workbook matching CTLS TMS Booking Fields.xlsx structure from scratch if template is missing."""
        wb = openpyxl.Workbook()
        ws_direct = wb.active
        ws_direct.title = "Direct Booking"
        ws_group = wb.create_sheet(title="Group Booking")

        # Styling
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        step_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        step_font = Font(name="Calibri", size=11, bold=True, color="1F4E78")

        # Setup Direct Booking
        ws_direct.cell(row=1, column=1, value="TMS Direct Booking: fields").font = Font(size=14, bold=True)
        ws_direct.cell(
            row=2,
            column=1,
            value="One row per booking. Fields marked * are mandatory in the TMS. (auto) fields are calculated by the TMS.",
        ).font = Font(italic=True)

        for col_idx, step, name, _, _, _ in DIRECT_BOOKING_COLUMNS:
            ws_direct.cell(row=4, column=col_idx, value=step).fill = step_fill
            ws_direct.cell(row=4, column=col_idx).font = step_font
            c = ws_direct.cell(row=5, column=col_idx, value=name)
            c.fill = header_fill
            c.font = header_font
            ws_direct.column_dimensions[get_column_letter(col_idx)].width = max(len(name) + 3, 14)

        # Setup Group Booking
        ws_group.cell(row=1, column=1, value="TMS Group Booking: fields").font = Font(size=14, bold=True)
        ws_group.cell(
            row=2,
            column=1,
            value="One row per LR (consignment). Booking, shipper and trip details repeat on every row of the same truck. Fields marked * are mandatory; (auto) fields are calculated by the TMS.",
        ).font = Font(italic=True)

        for col_idx, step, name, _, _, _, _ in GROUP_BOOKING_COLUMNS:
            ws_group.cell(row=4, column=col_idx, value=step).fill = step_fill
            ws_group.cell(row=4, column=col_idx).font = step_font
            c = ws_group.cell(row=5, column=col_idx, value=name)
            c.fill = header_fill
            c.font = header_font
            ws_group.column_dimensions[get_column_letter(col_idx)].width = max(len(name) + 3, 14)

        return wb

