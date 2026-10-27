import io
from PIL import Image
import pymupdf


def create_text_pdf(
    text: str = "Logistics Tax Invoice INV-2026-9081\nDate: 2026-10-27\nTotal Freight: 45000.00 INR\nConsignor: Global Logistics Ltd",
    pages: int = 1,
) -> bytes:
    """Generates an in-memory synthetic PDF with embedded text."""
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text(pymupdf.Point(50, 72), text, fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_scanned_pdf(pages: int = 1) -> bytes:
    """Generates an in-memory synthetic PDF containing a full-page raster image with no text layer."""
    # Create synthetic scanned image
    img = Image.new("RGB", (600, 800), color=(240, 240, 240))
    img_buf = io.BytesIO()
    img.save(img_buf, format="JPEG")
    img_bytes = img_buf.getvalue()

    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=img_bytes)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_mixed_pdf() -> bytes:
    """Generates a 2-page PDF: Page 1 with embedded text, Page 2 with a scanned raster image."""
    img = Image.new("RGB", (600, 800), color=(235, 235, 235))
    img_buf = io.BytesIO()
    img.save(img_buf, format="JPEG")
    img_bytes = img_buf.getvalue()

    doc = pymupdf.open()
    # Page 1: Text-based
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text(
        pymupdf.Point(50, 72),
        "LORRY RECEIPT / BILTY\nLR No: LR-883921\nVehicle No: MH-12-PQ-9988\nFrom: Mumbai To: Delhi",
        fontsize=12,
    )
    # Page 2: Scanned image
    p2 = doc.new_page(width=595, height=842)
    p2.insert_image(p2.rect, stream=img_bytes)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_encrypted_pdf(password: str = "confidential123") -> bytes:
    """Generates a password-protected PDF to test encryption rejection."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(pymupdf.Point(50, 72), "Encrypted Confidential Document", fontsize=12)
    pdf_bytes = doc.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw=password,
        owner_pw=password,
    )
    doc.close()
    return pdf_bytes


def create_synthetic_image(fmt: str = "PNG", width: int = 300, height: int = 300) -> bytes:
    """Generates a valid standalone image in memory."""
    img = Image.new("RGB", (width, height), color=(245, 245, 245))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()
