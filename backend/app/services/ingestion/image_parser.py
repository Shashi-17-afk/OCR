import io
from PIL import Image, UnidentifiedImageError

from backend.app.core.config import settings
from backend.app.schemas.document import PageProcessingResult, PageStatus
from backend.app.services.ingestion.exceptions import (
    MalformedDocumentError,
    FileTooLargeError,
)


class ImageParser:
    """Safely decodes and validates standalone image documents."""

    @staticmethod
    def parse(content: bytes) -> tuple[list[PageProcessingResult], list[str]]:
        """
        Validates the image stream, ensures image dimensions are safe,
        and returns a page result indicating that OCR is required.
        """
        warnings: list[str] = []
        try:
            image_stream = io.BytesIO(content)
            with Image.open(image_stream) as img:
                # 1. Structural integrity check
                img.verify()

            # Reopen to read metadata
            image_stream.seek(0)
            with Image.open(image_stream) as img:
                width, height = img.size

                # 2. Decompression bomb / dimension guard
                if width > settings.MAX_IMAGE_DIMENSION_PX or height > settings.MAX_IMAGE_DIMENSION_PX:
                    raise FileTooLargeError(
                        max_bytes=settings.MAX_IMAGE_DIMENSION_PX,
                        actual_bytes=max(width, height),
                    )

                if width < 10 or height < 10:
                    warnings.append(f"Image dimensions ({width}x{height}) are unusually small.")

            # Standalone images have no embedded text layer; OCR is required in subsequent phases
            page_result = PageProcessingResult(
                page_number=1,
                status=PageStatus.OCR_REQUIRED,
                has_embedded_text=False,
                is_scanned=True,
                char_count=0,
                word_count=0,
                extracted_text=None,
            )

            return [page_result], warnings

        except (UnidentifiedImageError, OSError, ValueError) as err:
            raise MalformedDocumentError(f"Corrupt or unreadable image stream: {str(err)}") from err
