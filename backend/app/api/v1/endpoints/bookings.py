from fastapi import APIRouter, Body, File, HTTPException, Query, Response, UploadFile, status

from backend.app.core.config import settings
from backend.app.schemas.classification import BookingType, LoadingPoint
from backend.app.schemas.error import ErrorResponse
from backend.app.schemas.extraction import TirunelveliExtractionResponse
from backend.app.schemas.hierarchy import TirunelveliHierarchyResponse
from backend.app.schemas.reconciliation import TirunelveliReconciliationResponse
from backend.app.services.export.excel import TirunelveliExcelExporter
from backend.app.services.extraction.tirunelveli.service import (
    TirunelveliExtractionService,
)
from backend.app.services.grouping.tirunelveli_linker import (
    TirunelveliDocumentLinker,
)
from backend.app.services.reconciliation.reconciler import (
    TirunelveliReconciliationEngine,
)
from backend.app.services.ingestion.exceptions import (
    EmptyFileError,
    EncryptedDocumentError,
    ExcessivePagesError,
    FileTooLargeError,
    MalformedDocumentError,
    UnsupportedFormatError,
)

router = APIRouter()


@router.post(
    "/tirunelveli/extract",
    response_model=TirunelveliExtractionResponse,
    status_code=status.HTTP_200_OK,
    summary="Tirunelveli: Classify Pages & Extract Raw Fields",
    description=(
        "Ingests a multi-page logistics document bundle for Tirunelveli. "
        "Classifies each page as MATERIAL_INVOICE, EWAY_BILL, SECURITY_COPY, "
        "LORRY_RECEIPT, or UNKNOWN_PAGE. Extracts raw fields with confidence scores "
        "and coordinates, preserving both raw and normalized LR numbers. "
        "Flags ambiguous entries for human review without silently dropping pages."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Empty or zero-byte file"},
        413: {"model": ErrorResponse, "description": "File exceeds maximum size limit"},
        415: {"model": ErrorResponse, "description": "Unsupported document format or signature"},
        422: {"model": ErrorResponse, "description": "Invalid parameters, malformed document, or unsupported loading point"},
    },
)
async def extract_tirunelveli_document(
    file: UploadFile = File(..., description="Document bundle (PDF, PNG, JPEG)"),
    loading_point: LoadingPoint = Query(
        ...,
        description="Mandatory loading point selection ('tirunelveli' or 'erode')",
    ),
    booking_type: BookingType = Query(
        ...,
        description="Mandatory booking type decided by staff ('direct' or 'group')",
    ),
    enable_ocr: bool = Query(
        default=True,
        description="Whether to run local OCR for scanned pages",
    ),
) -> TirunelveliExtractionResponse:
    """Classifies pages and extracts raw fields for Tirunelveli booking documents."""
    if loading_point == LoadingPoint.ERODE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Loading point 'erode' is scheduled for Client Phase 2 (Erode milestone). Only 'tirunelveli' is currently active.",
        )

    # Read bounded content
    max_read_bytes = settings.MAX_FILE_SIZE_BYTES + 1024
    content = await file.read(max_read_bytes)

    if len(content) > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Uploaded file exceeds maximum limit of {settings.MAX_FILE_SIZE_BYTES} bytes.",
        )

    filename = file.filename or "tirunelveli_document"

    try:
        response = TirunelveliExtractionService.process(
            content=content,
            original_filename=filename,
            booking_type=booking_type,
            enable_ocr=enable_ocr,
        )
        return response

    except EmptyFileError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err.message,
        ) from err

    except UnsupportedFormatError as err:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=err.message,
        ) from err

    except FileTooLargeError as err:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=err.message,
        ) from err

    except (EncryptedDocumentError, ExcessivePagesError, MalformedDocumentError) as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=err.message,
        ) from err


@router.post(
    "/tirunelveli/link",
    response_model=TirunelveliHierarchyResponse,
    status_code=status.HTTP_200_OK,
    summary="Tirunelveli: Link Documents & Build Booking Hierarchy",
    description=(
        "Ingests a multi-page logistics document bundle for Tirunelveli, classifies pages, "
        "extracts raw fields, and links documents into a structured truck booking hierarchy. "
        "Separates multi-truck uploads, preserves candidate links on evidence conflict, "
        "and routes unassignable pages into the unassigned pool with strict page accounting."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Empty or zero-byte file"},
        413: {"model": ErrorResponse, "description": "File exceeds maximum size limit"},
        415: {"model": ErrorResponse, "description": "Unsupported document format or signature"},
        422: {"model": ErrorResponse, "description": "Invalid parameters, malformed document, or unsupported loading point"},
    },
)
async def link_tirunelveli_document(
    file: UploadFile = File(..., description="Document bundle (PDF, PNG, JPEG)"),
    loading_point: LoadingPoint = Query(
        ...,
        description="Mandatory loading point selection ('tirunelveli' or 'erode')",
    ),
    booking_type: BookingType = Query(
        ...,
        description="Mandatory booking type decided by staff ('direct' or 'group')",
    ),
    enable_ocr: bool = Query(
        default=True,
        description="Whether to run local OCR for scanned pages",
    ),
) -> TirunelveliHierarchyResponse:
    """Links classified pages into truck dossiers and consignment hierarchies."""
    if loading_point == LoadingPoint.ERODE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Loading point 'erode' is scheduled for Client Phase 2 (Erode milestone). Only 'tirunelveli' is currently active.",
        )

    max_read_bytes = settings.MAX_FILE_SIZE_BYTES + 1024
    content = await file.read(max_read_bytes)

    if len(content) > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Uploaded file exceeds maximum limit of {settings.MAX_FILE_SIZE_BYTES} bytes.",
        )

    filename = file.filename or "tirunelveli_document"

    try:
        extraction_resp = TirunelveliExtractionService.process(
            content=content,
            original_filename=filename,
            booking_type=booking_type,
            enable_ocr=enable_ocr,
        )
        hierarchy_resp = TirunelveliDocumentLinker.link_documents(extraction_resp)
        return hierarchy_resp

    except EmptyFileError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err.message,
        ) from err

    except UnsupportedFormatError as err:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=err.message,
        ) from err

    except FileTooLargeError as err:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=err.message,
        ) from err

    except (EncryptedDocumentError, ExcessivePagesError, MalformedDocumentError) as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=err.message,
        ) from err


@router.post(
    "/tirunelveli/reconcile",
    response_model=TirunelveliReconciliationResponse,
    status_code=status.HTTP_200_OK,
    summary="Tirunelveli: Apply Business Rules & Reconcile Booking",
    description=(
        "Full Step 4C reconciliation pipeline: ingests Tirunelveli documents, links them, "
        "applies weight precedence (invoice gross weight governs), performs kg to MT conversion, "
        "applies freight rules (party freight vs shipper freight), compresses sequential invoice cells, "
        "handles duplicate physical pages safely, and cross-checks group totals against Security Copy."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Empty or zero-byte file"},
        413: {"model": ErrorResponse, "description": "File exceeds maximum size limit"},
        415: {"model": ErrorResponse, "description": "Unsupported document format or signature"},
        422: {"model": ErrorResponse, "description": "Invalid parameters, malformed document, or unsupported loading point"},
    },
)
async def reconcile_tirunelveli_document(
    file: UploadFile = File(..., description="Document bundle (PDF, PNG, JPEG)"),
    loading_point: LoadingPoint = Query(
        ...,
        description="Mandatory loading point selection ('tirunelveli' or 'erode')",
    ),
    booking_type: BookingType = Query(
        ...,
        description="Mandatory booking type decided by staff ('direct' or 'group')",
    ),
    enable_ocr: bool = Query(
        default=True,
        description="Whether to run local OCR for scanned pages",
    ),
) -> TirunelveliReconciliationResponse:
    """Applies PRD business rules and reconciliation checks to Tirunelveli booking documents."""
    if loading_point == LoadingPoint.ERODE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Loading point 'erode' is scheduled for Client Phase 2 (Erode milestone). Only 'tirunelveli' is currently active.",
        )

    max_read_bytes = settings.MAX_FILE_SIZE_BYTES + 1024
    content = await file.read(max_read_bytes)

    if len(content) > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Uploaded file exceeds maximum limit of {settings.MAX_FILE_SIZE_BYTES} bytes.",
        )

    filename = file.filename or "tirunelveli_document"

    try:
        extraction_resp = TirunelveliExtractionService.process(
            content=content,
            original_filename=filename,
            booking_type=booking_type,
            enable_ocr=enable_ocr,
        )
        hierarchy_resp = TirunelveliDocumentLinker.link_documents(extraction_resp)
        reconciled_resp = TirunelveliReconciliationEngine.reconcile(hierarchy_resp)
        reconciled_resp.page_extractions = extraction_resp.pages
        return reconciled_resp

    except EmptyFileError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err.message,
        ) from err

    except UnsupportedFormatError as err:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=err.message,
        ) from err

    except FileTooLargeError as err:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=err.message,
        ) from err

    except (EncryptedDocumentError, ExcessivePagesError, MalformedDocumentError) as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=err.message,
        ) from err


@router.post(
    "/tirunelveli/export-excel",
    status_code=status.HTTP_200_OK,
    summary="Tirunelveli: Reconcile Booking & Export Excel Workbook",
    description=(
        "Full Step 4D pipeline: processes Tirunelveli logistics documents through ingestion, "
        "classification, linking, and reconciliation, and generates a formatted, air-gapped .xlsx "
        "workbook ready for staff TMS entry. Preserves invoice ranges, leading zeros in LR numbers, "
        "proper numeric formats, visual review highlights, and complete page accounting."
    ),
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}
            },
            "description": "Formatted Excel workbook stream (.xlsx)",
        },
        400: {"model": ErrorResponse, "description": "Empty or zero-byte file"},
        413: {"model": ErrorResponse, "description": "File exceeds maximum size limit"},
        415: {"model": ErrorResponse, "description": "Unsupported document format or signature"},
        422: {"model": ErrorResponse, "description": "Invalid parameters, malformed document, or unsupported loading point"},
    },
)
async def export_tirunelveli_excel(
    file: UploadFile = File(..., description="Document bundle (PDF, PNG, JPEG)"),
    loading_point: LoadingPoint = Query(
        ...,
        description="Mandatory loading point selection ('tirunelveli' or 'erode')",
    ),
    booking_type: BookingType = Query(
        ...,
        description="Mandatory booking type decided by staff ('direct' or 'group')",
    ),
    enable_ocr: bool = Query(
        default=True,
        description="Whether to run local OCR for scanned pages",
    ),
) -> Response:
    """Reconciles booking documents and exports formatted Excel (.xlsx) workbook."""
    if loading_point == LoadingPoint.ERODE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Loading point 'erode' is scheduled for Client Phase 2 (Erode milestone). Only 'tirunelveli' is currently active.",
        )

    max_read_bytes = settings.MAX_FILE_SIZE_BYTES + 1024
    content = await file.read(max_read_bytes)

    if len(content) > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Uploaded file exceeds maximum limit of {settings.MAX_FILE_SIZE_BYTES} bytes.",
        )

    filename = file.filename or "tirunelveli_document"

    try:
        extraction_resp = TirunelveliExtractionService.process(
            content=content,
            original_filename=filename,
            booking_type=booking_type,
            enable_ocr=enable_ocr,
        )
        hierarchy_resp = TirunelveliDocumentLinker.link_documents(extraction_resp)
        reconciled_resp = TirunelveliReconciliationEngine.reconcile(hierarchy_resp)

        excel_bytes = TirunelveliExcelExporter.export(reconciled_resp)

        # Generate descriptive, safe download filename
        if reconciled_resp.truck_dossiers:
            d = reconciled_resp.truck_dossiers[0]
            date_clean = d.booking_date.replace("/", ".").replace("-", ".")
            download_filename = f"{d.truck_number}_{date_clean}_reconciled.xlsx"
        else:
            download_filename = f"{filename}_reconciled.xlsx"

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
        )

    except EmptyFileError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err.message,
        ) from err

    except UnsupportedFormatError as err:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=err.message,
        ) from err

    except FileTooLargeError as err:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=err.message,
        ) from err

    except (EncryptedDocumentError, ExcessivePagesError, MalformedDocumentError) as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=err.message,
        ) from err


@router.post(
    "/tirunelveli/export-excel-from-reconciliation",
    status_code=status.HTTP_200_OK,
    summary="Tirunelveli: Export Excel from Reconciliation Response JSON",
    description=(
        "Generates an Excel workbook directly from an existing Step 4C reconciliation JSON response. "
        "Enables instant Excel generation without re-uploading or re-processing document images."
    ),
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}
            },
            "description": "Formatted Excel workbook stream (.xlsx)",
        },
    },
)
async def export_tirunelveli_excel_from_reconciliation(
    reconciliation: TirunelveliReconciliationResponse = Body(..., description="Step 4C response payload"),
) -> Response:
    """Exports formatted Excel (.xlsx) from an existing Step 4C reconciliation payload."""
    excel_bytes = TirunelveliExcelExporter.export(reconciliation)

    if reconciliation.truck_dossiers:
        d = reconciliation.truck_dossiers[0]
        date_clean = d.booking_date.replace("/", ".").replace("-", ".")
        download_filename = f"{d.truck_number}_{date_clean}_reconciled.xlsx"
    else:
        download_filename = f"{reconciliation.original_filename}_reconciled.xlsx"

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
    )


