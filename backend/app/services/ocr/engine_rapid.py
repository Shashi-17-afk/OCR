from typing import Any, Optional
import numpy as np

from backend.app.core.logging import logger
from backend.app.services.ocr.base import BaseOCREngine, OCRItem, OCRResult
from backend.app.services.ocr.preprocessor import ImagePreprocessor


class RapidPaddleOCREngine(BaseOCREngine):
    """
    Local ONNX-accelerated OCR engine utilizing PP-OCRv4 models.
    Operates completely offline with zero telemetry or network calls.
    """

    def __init__(self) -> None:
        self._engine = None
        self._initialize_engine()

    def _initialize_engine(self) -> None:
        """Lazily initializes the RapidOCR ONNX model pipeline."""
        if self._engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR

                # Initialize RapidOCR with default embedded PP-OCRv4 ONNX models
                self._engine = RapidOCR()
                logger.info("Initialized local RapidOCR ONNX engine successfully.")
            except Exception as err:
                logger.error("Failed to initialize RapidOCR engine: %s", str(err))
                self._engine = None

    def is_available(self) -> bool:
        return self._engine is not None

    def extract(self, image_input: Any) -> OCRResult:
        """
        Executes local OCR inference on the provided image input.
        """
        if not self.is_available():
            raise RuntimeError("Local OCR engine is unavailable or failed to initialize.")

        # 1. Preprocess image (deskew, scale, color normalize)
        preprocessed_img, skew_angle = ImagePreprocessor.preprocess(image_input)

        try:
            # 2. Run local ONNX OCR inference
            ocr_output, _ = self._engine(preprocessed_img)
        except Exception as err:
            logger.error("Error during OCR inference: %s", err.__class__.__name__)
            raise RuntimeError(f"OCR inference execution failed: {err.__class__.__name__}") from err

        # 3. Handle empty or no-text result
        if not ocr_output:
            return OCRResult(
                text="",
                lines=[],
                mean_confidence=None,
                char_count=0,
                word_count=0,
            )

        # 4. Standardize recognized items
        lines: list[OCRItem] = []
        confidences: list[float] = []
        text_lines: list[str] = []

        for item in ocr_output:
            try:
                box_coords, recognized_text, conf_val = item
                text_clean = str(recognized_text).strip()
                if not text_clean:
                    continue

                # Parse confidence safely
                conf_float = round(float(conf_val), 4) if conf_val is not None else None
                if conf_float is not None:
                    confidences.append(conf_float)

                box_formatted = [
                    [round(float(pt[0]), 1), round(float(pt[1]), 1)] for pt in box_coords
                ]

                lines.append(
                    OCRItem(
                        text=text_clean,
                        confidence=conf_float,
                        box=box_formatted,
                    )
                )
                text_lines.append(text_clean)
            except (ValueError, TypeError, IndexError) as parse_err:
                logger.debug("Skipping unparseable OCR token: %s", str(parse_err))
                continue

        # 5. Cluster items into spatial reading lines (top-to-bottom, left-to-right)
        token_boxes: list[tuple[float, float, str]] = []
        for item in lines:
            if item.box and len(item.box) >= 4:
                y_mid = (item.box[0][1] + item.box[2][1]) / 2.0
                x_mid = (item.box[0][0] + item.box[2][0]) / 2.0
                token_boxes.append((y_mid, x_mid, item.text))
            else:
                token_boxes.append((0.0, 0.0, item.text))

        token_boxes.sort(key=lambda t: t[0])
        clustered_text_lines: list[str] = []
        curr_cluster: list[tuple[float, str]] = []
        curr_cluster_y: Optional[float] = None

        for y, x, txt in token_boxes:
            if curr_cluster_y is None or abs(y - curr_cluster_y) <= 14.0:
                curr_cluster.append((x, txt))
                curr_cluster_y = y if curr_cluster_y is None else (curr_cluster_y + y) / 2.0
            else:
                curr_cluster.sort(key=lambda t: t[0])
                clustered_text_lines.append("   ".join(t[1] for t in curr_cluster))
                curr_cluster = [(x, txt)]
                curr_cluster_y = y

        if curr_cluster:
            curr_cluster.sort(key=lambda t: t[0])
            clustered_text_lines.append("   ".join(t[1] for t in curr_cluster))

        full_text = "\n".join(clustered_text_lines) if clustered_text_lines else "\n".join(text_lines)
        char_count = len(full_text)
        word_count = len(full_text.split())
        mean_conf = (
            round(sum(confidences) / len(confidences), 4) if confidences else None
        )

        return OCRResult(
            text=full_text,
            lines=lines,
            mean_confidence=mean_conf,
            char_count=char_count,
            word_count=word_count,
        )
