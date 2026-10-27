import re
from typing import Tuple
import pymupdf

from backend.app.core.config import settings
from backend.app.schemas.document import PageProcessingResult, PageStatus
from backend.app.services.ingestion.exceptions import (
    EncryptedDocumentError,
    ExcessivePagesError,
    MalformedDocumentError,
)


class PDFParser:
    """Inspects and parses PDF documents using PyMuPDF."""

    @classmethod
    def parse(cls, content: bytes) -> Tuple[list[PageProcessingResult], list[str]]:
        """
        Parses a PDF document stream page by page.

        Returns:
            Tuple of (page_results, warnings)
        Raises:
            EncryptedDocumentError, ExcessivePagesError, MalformedDocumentError
        """
        warnings: list[str] = []
        doc = None
        try:
            doc = pymupdf.open(stream=content, filetype="pdf")
        except Exception as err:
            raise MalformedDocumentError(f"Unable to parse PDF stream: {str(err)}") from err

        try:
            # 1. Encryption check
            if doc.is_encrypted:
                raise EncryptedDocumentError("Document is encrypted or password-protected.")

            page_count = doc.page_count
            if page_count == 0:
                raise MalformedDocumentError("PDF contains 0 pages.")

            # 2. Page count limit check
            if page_count > settings.MAX_PDF_PAGES:
                raise ExcessivePagesError(
                    max_pages=settings.MAX_PDF_PAGES,
                    actual_pages=page_count,
                )

            # 3. Process each page individually
            results: list[PageProcessingResult] = []
            for page_idx in range(page_count):
                page_num = page_idx + 1
                try:
                    page = doc.load_page(page_idx)
                    page_result, page_warning = cls._inspect_page(page, page_num)
                    results.append(page_result)
                    if page_warning:
                        warnings.append(f"Page {page_num}: {page_warning}")
                except Exception as page_err:
                    results.append(
                        PageProcessingResult(
                            page_number=page_num,
                            status=PageStatus.PROCESSING_FAILED,
                            has_embedded_text=False,
                            is_scanned=False,
                            error_message=f"Failed to process page: {type(page_err).__name__}",
                        )
                    )

            return results, warnings

        finally:
            if doc is not None:
                doc.close()

    @classmethod
    def _inspect_page(
        cls, page: pymupdf.Page, page_num: int
    ) -> Tuple[PageProcessingResult, str | None]:
        """
        Inspects an individual PDF page to determine whether usable embedded text exists
        or if the page is a raster scan requiring OCR.
        """
        raw_text = page.get_text("text") or ""
        words = page.get_text("words") or []
        images = page.get_images() or []

        # Count printable alphanumeric characters
        alphanumeric_chars = re.sub(r"\s+", "", raw_text)
        char_count = len(raw_text)
        alphanumeric_count = len(alphanumeric_chars)
        word_count = len(words)

        page_rect = page.rect
        page_area = page_rect.width * page_rect.height if page_rect else 0.0

        # Heuristic: Check if raster images dominate the page area
        has_dominant_raster = False
        if images and page_area > 0:
            for img_info in images:
                xref = img_info[0]
                try:
                    img_rects = page.get_image_rects(xref)
                    for r in img_rects:
                        img_area = r.width * r.height
                        if img_area >= (0.60 * page_area):
                            has_dominant_raster = True
                            break
                except Exception:
                    pass

        # Case 1: Purely blank page (no text and no images)
        if alphanumeric_count == 0 and len(images) == 0:
            return (
                PageProcessingResult(
                    page_number=page_num,
                    status=PageStatus.EMPTY_PAGE,
                    has_embedded_text=False,
                    is_scanned=False,
                    char_count=0,
                    word_count=0,
                    extracted_text=None,
                ),
                "Page appears to be empty with no text or images.",
            )

        # Case 2: Dominant raster scan with minimal or no embedded text -> Scanned page
        if has_dominant_raster and alphanumeric_count < settings.MIN_TEXT_CHARS_PER_PAGE:
            return (
                PageProcessingResult(
                    page_number=page_num,
                    status=PageStatus.OCR_REQUIRED,
                    has_embedded_text=False,
                    is_scanned=True,
                    char_count=0,
                    word_count=0,
                    extracted_text=None,
                ),
                None,
            )

        # Case 3: Images present with zero or negligible text
        if alphanumeric_count < settings.MIN_TEXT_CHARS_PER_PAGE and len(images) > 0:
            return (
                PageProcessingResult(
                    page_number=page_num,
                    status=PageStatus.OCR_REQUIRED,
                    has_embedded_text=False,
                    is_scanned=True,
                    char_count=0,
                    word_count=0,
                    extracted_text=None,
                ),
                None,
            )

        # Case 4: Text below minimum threshold without images
        if 0 < alphanumeric_count < settings.MIN_TEXT_CHARS_PER_PAGE:
            return (
                PageProcessingResult(
                    page_number=page_num,
                    status=PageStatus.OCR_REQUIRED,
                    has_embedded_text=False,
                    is_scanned=True,
                    char_count=char_count,
                    word_count=word_count,
                    extracted_text=None,
                ),
                f"Page contains only {alphanumeric_count} characters; insufficient embedded text, OCR required.",
            )

        # Case 5: Usable embedded text present
        return (
            PageProcessingResult(
                page_number=page_num,
                status=PageStatus.TEXT_EXTRACTED,
                has_embedded_text=True,
                is_scanned=False,
                char_count=char_count,
                word_count=word_count,
                extracted_text=raw_text.strip(),
            ),
            None,
        )
