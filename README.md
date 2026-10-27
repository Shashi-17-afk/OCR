# Logistics Document Processing & OCR Service

Production-oriented, secure on-premises document processing and OCR backend for logistics documents (Invoices and Lorry Receipts).

## Architecture & Status

- **Status:** Phase 2 Complete (Document Ingestion, Binary Signature Verification & Embedded-Text Extraction)
- **Runtime:** Python 3.14+ (64-bit on Windows)
- **Framework:** FastAPI with Uvicorn
- **PDF & Image Processing:** PyMuPDF (`pymupdf`) and Pillow (`PIL`)
- **Validation:** Pydantic v2 & Pydantic-Settings
- **Security:** Air-gapped ready, strict confidentiality logging filter, in-memory bounded processing, zero cloud telemetry, safe error masking.

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

---

## Running the Application

To start the FastAPI backend server on Windows:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Endpoints Available
- **Document Ingestion:** `POST http://127.0.0.1:8000/api/v1/documents/ingest`
- **Health Check (Root):** `http://127.0.0.1:8000/health`
- **Health Check (API v1):** `http://127.0.0.1:8000/api/v1/health`
- **Service Info:** `http://127.0.0.1:8000/`
- **Interactive OpenAPI Docs (when DEBUG=true):** `http://127.0.0.1:8000/docs`

---

## Document Ingestion Behavior

### Endpoint: `POST /api/v1/documents/ingest`
Accepts `multipart/form-data` with a `file` field.

- **Supported Formats:** PDF (`.pdf`), PNG (`.png`), JPEG/JPG (`.jpg`, `.jpeg`).
- **Signature Verification:** Checks true binary magic bytes (`%PDF-`, PNG header, JPEG SOI marker) rather than trusting client file extensions or MIME headers.
- **Embedded-Text vs Scanned PDFs:**
  - Evaluates each PDF page individually.
  - If usable embedded text is found, extracts text and sets page status to `TEXT_EXTRACTED`.
  - If a page is a scanned image or has insufficient embedded text (< 40 characters), sets status explicitly to `OCR_REQUIRED` with `extracted_text: null`.
  - Supports mixed PDFs containing both digital and scanned pages (`overall_status: "MIXED_CONTENT"`).
- **Standalone Images:** Validates structure and dimensions (protecting against decompression bombs) and returns `overall_status: "VALIDATED_IMAGE"` with page status `OCR_REQUIRED`.
- **In-Memory Bounded Security:** Files are processed directly in memory without writing sensitive customer documents to disk.
- **Confidentiality:** Application logs record only document UUIDs, format, page count, and latency. Document contents and extracted text are strictly omitted from logs.

---

## Running Tests

Execute the automated test suite with pytest:
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

---

## Project Structure (Phase 2)

```
d:\BeSpoke\
├── .env.example              # Baseline configuration template
├── .gitignore                # Protects secrets, venvs, models, and confidential documents
├── requirements.txt          # Phase 2 dependencies (fastapi, pymupdf, pillow, pydantic, pytest)
├── README.md                 # Setup, execution, and security documentation
├── backend/
│   └── app/
│       ├── __init__.py
│       ├── main.py           # FastAPI application, exception handlers & lifespan
│       ├── api/
│       │   ├── __init__.py
│       │   └── v1/
│       │       ├── __init__.py
│       │       ├── router.py # Aggregated API v1 router
│       │       └── endpoints/
│       │           ├── __init__.py
│       │           ├── health.py    # /health endpoint
│       │           └── documents.py # /documents/ingest endpoint
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py     # Pydantic BaseSettings & configurable limits
│       │   └── logging.py    # ConfidentialityFilter & secure logging
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── error.py      # Standard safe error response model
│       │   ├── health.py     # Standard health check response model
│       │   └── document.py   # Document ingestion request/response schemas
│       └── services/
│           ├── __init__.py
│           └── ingestion/
│               ├── __init__.py
│               ├── exceptions.py   # Ingestion domain exceptions
│               ├── validator.py    # Binary magic byte & size validation
│               ├── pdf_parser.py   # PyMuPDF page inspection & text extraction
│               ├── image_parser.py # Safe image decoder & dimension validation
│               └── service.py      # DocumentIngestionService orchestrator
└── tests/
    ├── __init__.py
    ├── conftest.py           # Pytest fixtures and TestClient initialization
    ├── helpers.py            # Synthetic document generator helpers
    ├── test_error_handling.py# Safe error response & 500 masking tests
    ├── test_health.py        # Health check & root endpoint tests
    ├── test_ingestion.py     # Document ingestion, scan detection & edge cases
    └── test_logging.py       # Confidentiality log filter tests
```