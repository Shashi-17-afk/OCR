import io
from typing import Optional
from PIL import Image
import fitz

from backend.app.schemas.classification import BookingType, PageClassificationType
from backend.app.schemas.erode_extraction import (
    ErodeDespatchSheet,
    ErodeExtractionResponse,
    ErodeLRSheet,
    ErodePageExtraction,
)
from backend.app.services.classification.erode_classifier import ErodePageClassifier
from backend.app.services.extraction.erode.despatch_extractor import ErodeDespatchExtractor
from backend.app.services.extraction.erode.lr_sheet_extractor import ErodeLRSheetExtractor
from backend.app.services.ingestion.validator import FileValidator
from backend.app.services.ocr.factory import get_ocr_engine


class ErodeExtractionService:
    """Orchestrates ingestion, classification, and extraction for Erode booking documents."""

    @classmethod
    def process(
        cls,
        content: bytes,
        original_filename: str,
        booking_type: BookingType,
        enable_ocr: bool = True,
    ) -> ErodeExtractionResponse:
        # 1. Validate magic bytes and boundaries
        FileValidator.detect_and_validate(content, original_filename)

        doc = fitz.open(stream=content, filetype="pdf")
        page_extractions: list[ErodePageExtraction] = []
        found_despatch: Optional[ErodeDespatchSheet] = None
        found_lr_sheet: Optional[ErodeLRSheet] = None
        warnings: list[str] = []

        ocr_engine = get_ocr_engine() if enable_ocr else None

        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            page = doc[page_idx]

            # Extract digital text or run OCR
            text = page.get_text()
            page_image: Optional[Image.Image] = None

            # Render page pixmap if OCR or cropping needed
            pix = page.get_pixmap(dpi=150)
            page_image = Image.open(io.BytesIO(pix.tobytes("png")))

            if (not text or len(text.strip()) < 40) and ocr_engine:
                ocr_result = ocr_engine.extract(page_image)
                text = ocr_result.text

            # Classify page
            class_res = ErodePageClassifier.classify_page(text, page_number=page_num)

            despatch_data: Optional[ErodeDespatchSheet] = None
            lr_data: Optional[ErodeLRSheet] = None
            page_warns: list[str] = []

            if class_res.classification == PageClassificationType.DESPATCH_SHEET:
                despatch_data = ErodeDespatchExtractor.extract(text, page_number=page_num)
                if not found_despatch:
                    found_despatch = despatch_data

            elif class_res.classification == PageClassificationType.LORRY_RECEIPT:
                lr_data = ErodeLRSheetExtractor.extract(
                    text=text,
                    page_number=page_num,
                    page_image=page_image,
                )
                if not found_lr_sheet:
                    found_lr_sheet = lr_data
            else:
                page_warns.append("Page could not be definitively classified as Erode LR or Despatch sheet.")

            page_extractions.append(
                ErodePageExtraction(
                    page_number=page_num,
                    classification=class_res.classification,
                    confidence=class_res.confidence,
                    despatch=despatch_data,
                    lr_sheet=lr_data,
                    warnings=page_warns,
                )
            )

        doc.close()

        truck_no = (
            (found_lr_sheet and found_lr_sheet.truck_number)
            or (found_despatch and found_despatch.truck_number)
        )
        date_str = (
            (found_despatch and found_despatch.date)
            or (found_lr_sheet and found_lr_sheet.date)
        )

        if not found_lr_sheet:
            warnings.append("No LR Sheet found in the uploaded bundle.")
        if not found_despatch:
            warnings.append("No Despatch Details sheet found in the uploaded bundle.")

        return ErodeExtractionResponse(
            truck_number=truck_no,
            date=date_str,
            loading_point="erode",
            booking_type=booking_type.value,
            despatch_sheet=found_despatch,
            lr_sheet=found_lr_sheet,
            pages=page_extractions,
            extraction_warnings=warnings,
        )

