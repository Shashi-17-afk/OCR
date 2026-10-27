# Logistics Document Processing & OCR Service

Production-oriented, secure on-premises document processing and OCR backend for logistics documents (Invoices and Lorry Receipts).

## Architecture & Status

- **Status:** Phase 3 Complete (Local OCR Integration, Engine Abstraction, Preprocessing & Scanned PDF/Image Support)
- **Runtime:** Python 3.14+ (64-bit on Windows)
- **Framework:** FastAPI with Uvicorn
- **Local OCR Engine:** ONNX Runtime with PP-OCRv4 models (`rapidocr-onnxruntime`)
- **Image Preprocessing:** OpenCV (`opencv-python`) & Pillow (`PIL`) for auto-deskewing, contrast normalization, and dimension bounds
- **PDF Processing:** PyMuPDF (`pymupdf`)
- **Validation:** Pydantic v2 & Pydantic-Settings
- **Security:** Air-gapped verified, strict confidentiality logging filter, zero cloud telemetry, safe error masking.

---

## OCR Compatibility & Engine Evaluation (Python 3.14)

During Phase 3 evaluation:
- The standard `paddleocr` package relies on `paddlepaddle` as its underlying C++ deep learning engine. However, `paddlepaddle` does **not** provide precompiled binary wheels for Python 3.14 on Windows on PyPI (`ERROR: No matching distribution found for paddlepaddle`).
- Rather than forcing a disruptive Python downgrade or breaking the virtual environment, we adopted `rapidocr-onnxruntime`. This runs the **exact same PaddleOCR PP-OCRv4 detection and recognition models** compiled into ONNX format via `onnxruntime` (which natively supports Python 3.14 on Windows).
- **Offline Verified:** The ONNX model weights are self-contained within the package distribution (12 MB). The system has been validated to load models and execute inference with network sockets completely severed.
- **Pluggable Architecture:** All OCR operations are encapsulated behind the `BaseOCREngine` abstract interface (`backend/app/services/ocr/base.py`). If native PaddlePaddle or Tesseract is required in a future environment, a new adapter can be swapped in without modifying business logic.

---

## Windows Setup Instructions

### 1. Prerequisites
Ensure Python 3.10+ (64-bit) is installed and available in PowerShell:
```powershell
python --version
```

### 2. Virtual Environment Setup
Open PowerShell in the project root (`d:\BeSpoke`):
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```
*(If script execution is disabled on your system, run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`)*

### 3. Install Dependencies
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. Environment Configuration
Copy the example environment configuration:
```powershell
Copy-Item .env.example .env
```

Key environment variables in `.env`:
- `OCR_ENABLED=true` (Toggle OCR processing on/off)
- `OCR_ENGINE=rapidocr` (`rapidocr` for production local ONNX, `mock` for testing)
- `OCR_DPI=300` (Rasterization resolution for scanned PDF pages)
- `ENABLE_DESKEW=true` (Automatic text tilt detection and deskewing)

---

## Running the Application

To start the FastAPI backend server on Windows:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Endpoints Available
- **Document Ingestion & OCR:** `POST http://127.0.0.1:8000/api/v1/documents/ingest?enable_ocr=true`
- **Health Check (Root):** `http://127.0.0.1:8000/health`
- **Health Check (API v1):** `http://127.0.0.1:8000/api/v1/health`
- **Interactive OpenAPI Docs (when DEBUG=true):** `http://127.0.0.1:8000/docs`

---

## Document Ingestion & OCR Processing Pipeline

### Endpoint: `POST /api/v1/documents/ingest`
Accepts `multipart/form-data` with:
- `file`: PDF, PNG, or JPEG binary file.
- `enable_ocr` *(query param, default `true`)*: Whether to execute local OCR on scanned pages and images.

### Pipeline Behavior:
1. **Binary Content Validation:** Validates magic byte signatures (`%PDF-`, PNG, JPEG) and enforces size limits.
2. **Native Embedded-Text Detection:** If a PDF page contains $\ge 40$ characters of usable digital text and no dominant raster scan, text is extracted directly (`extraction_method: "EMBEDDED_TEXT"`). OCR confidence is reported as `null` (never fabricated).
3. **Scanned PDF Pages:** If a page is dominated by raster images, it is rendered at 300 DPI in memory, deskewed via OpenCV, and processed with local ONNX OCR (`extraction_method: "OCR"`).
4. **Standalone Images:** Validated, deskewed, and recognized via local OCR.
5. **Mixed PDFs:** Automatically supports multi-page documents containing both native text pages and scanned pages (`overall_status: "MIXED_CONTENT"` or `"TEXT_EXTRACTED"`).
6. **Output Metadata:** Each recognized segment includes the text string, bounding box polygon coordinates (`[[x1,y1], [x2,y2], [x3,y3], [x4,y4]]`), and confidence score.

---

## Running Automated Tests

Execute the full automated test suite with pytest:
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

---

## Project Structure (Phase 3)

```
d:\BeSpoke\
├── .env.example              # Baseline configuration template
├── .gitignore                # Protects secrets, venvs, models, and confidential documents
├── requirements.txt          # Phase 3 dependencies (FastAPI, PyMuPDF, RapidOCR, OpenCV, Pillow)
├── README.md                 # Architecture, setup, and execution documentation
├── backend/
│   └── app/
│       ├── __init__.py
│       ├── main.py           # FastAPI application & lifecycle
│       ├── api/
│       │   ├── __init__.py
│       │   └── v1/
│       │       ├── __init__.py
│       │       ├── router.py # Aggregated API v1 router
│       │       └── endpoints/
│       │           ├── __init__.py
│       │           ├── health.py    # /health endpoint
│       │           └── documents.py # /documents/ingest endpoint with enable_ocr
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py     # Application limits & OCR configuration
│       │   └── logging.py    # ConfidentialityFilter (no document text logged)
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── error.py      # ErrorResponse model
│       │   ├── health.py     # HealthResponse model
│       │   └── document.py   # Document ingestion, OCRLineResult & Page schemas
│       └── services/
│           ├── __init__.py
│           ├── ingestion/
│           │   ├── __init__.py
│           │   ├── exceptions.py   # Ingestion domain exceptions
│           │   ├── validator.py    # Binary magic byte & size validation
│           │   ├── pdf_parser.py   # PyMuPDF page inspection & OCR raster routing
│           │   ├── image_parser.py # Safe image decoder & OCR runner
│           │   └── service.py      # DocumentIngestionService orchestrator
│           └── ocr/
│               ├── __init__.py
│               ├── base.py         # BaseOCREngine, OCRItem, OCRResult abstractions
│               ├── preprocessor.py # Deskewing, scaling, and contrast preprocessing
│               ├── engine_rapid.py # Local RapidOCR (PP-OCRv4 ONNX) engine
│               ├── engine_mock.py  # MockOCREngine for deterministic tests
│               └── factory.py      # get_ocr_engine singleton factory
└── tests/
    ├── __init__.py
    ├── conftest.py           # Pytest fixtures and TestClient initialization
    ├── helpers.py            # Synthetic document generator helpers
    ├── test_error_handling.py# Safe error response & 500 masking tests
    ├── test_health.py        # Health check & root endpoint tests
    ├── test_ingestion.py     # Ingestion validation, scan detection & edge cases
    ├── test_logging.py       # Confidentiality log filter tests
    └── test_ocr.py           # Local OCR tests, mixed PDFs, deskewing & mock tests
```