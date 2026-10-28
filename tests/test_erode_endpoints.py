import io
import openpyxl
from fastapi import status
from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from tests.fixtures.synthetic_erode import create_synthetic_erode_bundle_pdf
from tests.fixtures.synthetic_tirunelveli import create_synthetic_tirunelveli_direct_pdf

client = TestClient(app, raise_server_exceptions=False)


def test_erode_extract_endpoint():
    """Verifies that the /erode/extract endpoint correctly extracts Erode documents."""
    pdf_bytes = create_synthetic_erode_bundle_pdf(is_direct=False)
    resp = client.post(
        "/api/v1/bookings/erode/extract?booking_type=group&enable_ocr=false",
        files={"file": ("erode_bundle.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["truck_number"] == "TN52L0517"
    assert data["loading_point"] == "erode"
    assert data["booking_type"] == "group"
    assert data["despatch_sheet"] is not None
    assert data["lr_sheet"] is not None
    assert len(data["despatch_sheet"]["rows"]) == 4
    assert len(data["lr_sheet"]["rows"]) == 3


def test_erode_reconcile_endpoint():
    """Verifies that the /erode/reconcile endpoint performs complete reconciliation."""
    pdf_bytes = create_synthetic_erode_bundle_pdf(is_direct=False)
    resp = client.post(
        "/api/v1/bookings/erode/reconcile?booking_type=group&enable_ocr=false",
        files={"file": ("erode_bundle.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["loading_point"] == "erode"
    assert len(data["truck_dossiers"]) == 1

    dossier = data["truck_dossiers"][0]
    assert len(dossier["reconciled_consignments"]) == 3
    assert dossier["truck_number"] == "TN52L0517"
    assert dossier["truck_total_packages"] == 60
    assert dossier["truck_total_weight_mt"] == 26.694


def test_erode_export_excel_endpoint():
    """Verifies end-to-end Excel generation for Erode bundles."""
    pdf_bytes = create_synthetic_erode_bundle_pdf(is_direct=False)
    resp = client.post(
        "/api/v1/bookings/erode/export-excel?booking_type=group&enable_ocr=false",
        files={"file": ("erode_bundle.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "TN52L0517" in resp.headers["content-disposition"]

    # Verify openpyxl workbook
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    assert "Consignments" in wb.sheetnames
    ws = wb["Consignments"]

    # Check banner
    banner = ws["A1"].value
    assert "CTLS TMS EXPORT - ERODE" in banner

    # Check row 3 (first consignment)
    truck_cell = ws["A3"].value
    lr_cell = ws["C3"].value
    inv_cell = ws["G3"].value
    wt_cell = ws["L3"].value
    frt_cell = ws["M3"].value

    assert truck_cell == "TN52L0517"
    assert lr_cell == "29738"
    assert inv_cell == "1250510477"
    assert wt_cell == 1.354
    assert frt_cell == 2505.0


def test_unified_export_endpoints():
    """Verifies that unified /export-excel routes to both Tirunelveli and Erode."""
    # 1. Unified with Erode
    erode_bytes = create_synthetic_erode_bundle_pdf(is_direct=True)
    resp1 = client.post(
        "/api/v1/bookings/export-excel?loading_point=erode&booking_type=direct&enable_ocr=false",
        files={"file": ("erode_direct.pdf", erode_bytes, "application/pdf")},
    )
    assert resp1.status_code == status.HTTP_200_OK
    assert "TN52AD9720" in resp1.headers["content-disposition"]

    # 2. Unified with Tirunelveli
    tiru_bytes = create_synthetic_tirunelveli_direct_pdf()
    resp2 = client.post(
        "/api/v1/bookings/export-excel?loading_point=tirunelveli&booking_type=direct&enable_ocr=false",
        files={"file": ("tiru_direct.pdf", tiru_bytes, "application/pdf")},
    )
    assert resp2.status_code == status.HTTP_200_OK
    assert "TN52Y7426" in resp2.headers["content-disposition"]

