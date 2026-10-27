import time
import uuid

from backend.app.core.logging import logger
from backend.app.schemas.document import (
    DocumentIngestResponse,
    DocumentOverallStatus,
    PageStatus,
)
from backend.app.services.ingestion.image_parser import ImageParser
from backend.app.services.ingestion.pdf_parser import PDFParser
from backend.app.services.ingestion.validator import FileValidator


class DocumentIngestionService:
    """Orchestrates document validation, format detection, and embedded-text extraction."""

    @classmethod
    def process_document(cls, content: bytes, original_filename: str) -> DocumentIngestResponse:
        """
        Executes the ingestion and text-extraction pipeline on in-memory binary data.
        Ensures bounded in-memory processing without writing sensitive files to disk.
        """
        start_time = time.perf_counter()
        doc_id = str(uuid.uuid4())

        # 1. Validation and signature detection
        detected_type, safe_filename = FileValidator.detect_and_validate(
            content=content,
            filename=original_filename,
        )

        # 2. Branch parsing based on verified signature
        if detected_type == "pdf":
            pages, warnings = PDFParser.parse(content)
        elif detected_type in ("png", "jpeg"):
            pages, warnings = ImageParser.parse(content)
        else:
            pages, warnings = [], ["Unrecognized document format."]

        # 3. Determine aggregated document status
        overall_status = cls._determine_overall_status(detected_type, pages)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # 4. Safe logging (Never log document text or user contents)
        logger.info(
            "Ingested doc_id=%s format=%s pages=%d status=%s size_bytes=%d duration_ms=%.2f",
            doc_id,
            detected_type,
            len(pages),
            overall_status.value,
            len(content),
            elapsed_ms,
        )

        return DocumentIngestResponse(
            document_id=doc_id,
            original_filename=safe_filename,
            file_type=detected_type,
            file_size_bytes=len(content),
            page_count=len(pages),
            overall_status=overall_status,
            pages=pages,
            warnings=warnings,
        )

    @staticmethod
    def _determine_overall_status(
        file_type: str, pages: list
    ) -> DocumentOverallStatus:
        if file_type in ("png", "jpeg"):
            return DocumentOverallStatus.VALIDATED_IMAGE

        if not pages:
            return DocumentOverallStatus.OCR_REQUIRED

        text_pages = sum(1 for p in pages if p.status == PageStatus.TEXT_EXTRACTED)
        ocr_pages = sum(1 for p in pages if p.status in (PageStatus.OCR_REQUIRED, PageStatus.EMPTY_PAGE))

        if text_pages == len(pages):
            return DocumentOverallStatus.TEXT_EXTRACTED
        if ocr_pages == len(pages):
            return DocumentOverallStatus.OCR_REQUIRED
        return DocumentOverallStatus.MIXED_CONTENT
