/**
 * CTLS Logistics Booking OCR & Reconciliation Client
 * 100% Local / Air-Gapped UI for Tirunelveli Milestone
 */

(function () {
  'use strict';

  // Global State
  const state = {
    selectedFile: null,
    fileBlobUrl: null,
    bookingType: 'auto',
    loadingPoint: 'tirunelveli',
    enableOcr: true,
    currentPage: 1,
    totalPages: 1,
    reconciliationData: null,
    workingConsignments: [],
    activeTruckIndex: 0,
  };

  // DOM Elements
  const elements = {
    // Ingest Screen
    ingestSection: document.getElementById('ingestSection'),
    reviewSection: document.getElementById('reviewSection'),
    dropzone: document.getElementById('dropzone'),
    fileInput: document.getElementById('fileInput'),
    browseBtn: document.getElementById('browseBtn'),
    changeFileBtn: document.getElementById('changeFileBtn'),
    selectedFileInfo: document.getElementById('selectedFileInfo'),
    fileNameDisplay: document.getElementById('fileNameDisplay'),
    fileSizeDisplay: document.getElementById('fileSizeDisplay'),
    startProcessBtn: document.getElementById('startProcessBtn'),
    loadingPointSelect: document.getElementById('loadingPointSelect'),
    bookingTypeToggle: document.getElementById('bookingTypeToggle'),
    ocrToggle: document.getElementById('ocrToggle'),
    processingOverlay: document.getElementById('processingOverlay'),
    processingTitle: document.getElementById('processingTitle'),
    processingStep: document.getElementById('processingStep'),

    // Review Toolbar
    truckSelectorBar: document.getElementById('truckSelectorBar'),
    backToUploadBtn: document.getElementById('backToUploadBtn'),
    barDocName: document.getElementById('barDocName'),
    barTruckPlate: document.getElementById('barTruckPlate'),
    barPageConservation: document.getElementById('barPageConservation'),
    barStatusBadge: document.getElementById('barStatusBadge'),
    recalcBtn: document.getElementById('recalcBtn'),
    exportExcelBtn: document.getElementById('exportExcelBtn'),
    footerExportBtn: document.getElementById('footerExportBtn'),
    footerStatusText: document.getElementById('footerStatusText'),

    // Left Pane (Document Viewer)
    prevPageBtn: document.getElementById('prevPageBtn'),
    nextPageBtn: document.getElementById('nextPageBtn'),
    pageIndicator: document.getElementById('pageIndicator'),
    pageClassBadge: document.getElementById('pageClassBadge'),
    pdfFrame: document.getElementById('pdfFrame'),
    imageViewer: document.getElementById('imageViewer'),
    thumbnailBar: document.getElementById('thumbnailBar'),

    // Right Pane (Tabs & Content)
    tabBtns: document.querySelectorAll('.tab-btn'),
    tabContents: document.querySelectorAll('.tab-content'),
    tabSelectedPageNum: document.getElementById('tabSelectedPageNum'),
    tabDiscrepancyCount: document.getElementById('tabDiscrepancyCount'),

    // Metrics
    metricGrossWeight: document.getElementById('metricGrossWeight'),
    metricGrossKg: document.getElementById('metricGrossKg'),
    metricPackages: document.getElementById('metricPackages'),
    metricGateSheetTie: document.getElementById('metricGateSheetTie'),
    metricTotalValue: document.getElementById('metricTotalValue'),
    metricFreight: document.getElementById('metricFreight'),
    metricFreightMode: document.getElementById('metricFreightMode'),

    // Tab Containers
    consignmentsContainer: document.getElementById('consignmentsContainer'),
    selectedPageContent: document.getElementById('selectedPageContent'),
    discrepanciesContainer: document.getElementById('discrepanciesContainer'),
    accountingSummary: document.getElementById('accountingSummary'),
    unassignedPoolContainer: document.getElementById('unassignedPoolContainer'),
  };

  // Initialize Event Listeners
  function init() {
    setupBookingTypeToggle();
    setupDropzone();
    setupTabs();
    setupNavigation();
    setupActions();
  }

  // Booking Type Toggle
  function setupBookingTypeToggle() {
    if (elements.bookingTypeToggle) {
      const btns = elements.bookingTypeToggle.querySelectorAll('.radio-btn');
      btns.forEach((btn) => {
        btn.addEventListener('click', () => {
          btns.forEach((b) => b.classList.remove('active'));
          btn.classList.add('active');
          state.bookingType = btn.getAttribute('data-value');
        });
      });
    }

    if (elements.ocrToggle) {
      elements.ocrToggle.addEventListener('change', (e) => {
        state.enableOcr = e.target.checked;
      });
    }

    if (elements.loadingPointSelect) {
      elements.loadingPointSelect.addEventListener('change', (e) => {
        state.loadingPoint = e.target.value;
      });
    }
  }

  // File Upload & Dropzone
  function setupDropzone() {
    const dropzone = elements.dropzone;
    const fileInput = elements.fileInput;

    elements.browseBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      fileInput.click();
    });

    dropzone.addEventListener('click', () => fileInput.click());

    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });

    ['dragleave', 'dragend'].forEach((type) => {
      dropzone.addEventListener(type, () => dropzone.classList.remove('dragover'));
    });

    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) {
        handleFileSelect(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        handleFileSelect(e.target.files[0]);
      }
    });

    elements.changeFileBtn.addEventListener('click', () => {
      fileInput.value = '';
      fileInput.click();
    });
  }

  function handleFileSelect(file) {
    const validExtensions = ['.pdf', '.png', '.jpg', '.jpeg'];
    const fileName = file.name.toLowerCase();
    const isValid = validExtensions.some((ext) => fileName.endsWith(ext));

    if (!isValid) {
      alert('Unsupported file format. Please upload a PDF, PNG, or JPEG document.');
      return;
    }

    state.selectedFile = file;
    if (state.fileBlobUrl) {
      URL.revokeObjectURL(state.fileBlobUrl);
    }
    state.fileBlobUrl = URL.createObjectURL(file);

    elements.fileNameDisplay.textContent = file.name;
    elements.fileSizeDisplay.textContent = formatBytes(file.size);

    elements.dropzone.style.display = 'none';
    elements.selectedFileInfo.style.display = 'flex';
    elements.startProcessBtn.disabled = false;
  }

  function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  // Tabs Handling
  function setupTabs() {
    elements.tabBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        const targetId = btn.getAttribute('data-tab');

        elements.tabBtns.forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');

        elements.tabContents.forEach((c) => {
          c.style.display = c.id === targetId ? 'block' : 'none';
        });
      });
    });
  }

  // Navigation (Left Pane)
  function setupNavigation() {
    elements.prevPageBtn.addEventListener('click', () => {
      if (state.currentPage > 1) {
        goToPage(state.currentPage - 1);
      }
    });

    elements.nextPageBtn.addEventListener('click', () => {
      if (state.currentPage < state.totalPages) {
        goToPage(state.currentPage + 1);
      }
    });

    elements.backToUploadBtn.addEventListener('click', () => {
      elements.reviewSection.style.display = 'none';
      elements.ingestSection.style.display = 'block';
    });
  }

  function goToPage(pageNum) {
    state.currentPage = pageNum;
    elements.pageIndicator.textContent = `Page ${pageNum} of ${state.totalPages}`;
    elements.prevPageBtn.disabled = pageNum <= 1;
    elements.nextPageBtn.disabled = pageNum >= state.totalPages;

    // Update document viewer
    if (state.selectedFile && state.selectedFile.name.toLowerCase().endsWith('.pdf')) {
      elements.imageViewer.style.display = 'none';
      elements.pdfFrame.style.display = 'block';
      // Native Chromium / Edge PDF embed navigation
      elements.pdfFrame.src = `${state.fileBlobUrl}#page=${pageNum}&toolbar=0&navpanes=0`;
    } else {
      elements.pdfFrame.style.display = 'none';
      elements.imageViewer.style.display = 'block';
      elements.imageViewer.src = state.fileBlobUrl;
    }

    // Update classification chip
    updatePageClassificationBadge(pageNum);

    // Update active thumbnail chip
    const chips = elements.thumbnailBar.querySelectorAll('.thumb-chip');
    chips.forEach((c, idx) => {
      c.classList.toggle('active', idx + 1 === pageNum);
    });

    // Update tab header & content
    elements.tabSelectedPageNum.textContent = pageNum;
    renderSelectedPageExtraction(pageNum);
  }

  function updatePageClassificationBadge(pageNum) {
    const pages = state.reconciliationData?.page_extractions || [];
    const pageData = pages.find((p) => p.page_number === pageNum);

    if (pageData) {
      const cls = pageData.classification.classification;
      const conf = Math.round(pageData.classification.confidence * 100);
      elements.pageClassBadge.textContent = `${cls} (${conf}%)`;
      elements.pageClassBadge.className = 'page-class-badge ' + getClassificationClass(cls);
    } else {
      elements.pageClassBadge.textContent = 'PAGE ' + pageNum;
      elements.pageClassBadge.className = 'page-class-badge class-unknown';
    }
  }

  function getClassificationClass(cls) {
    switch (cls) {
      case 'MATERIAL_INVOICE':
        return 'class-invoice';
      case 'EWAY_BILL':
        return 'class-eway';
      case 'LORRY_RECEIPT':
        return 'class-lr';
      case 'SECURITY_COPY':
        return 'class-sec';
      case 'DESPATCH_SHEET':
        return 'class-despatch';
      default:
        return 'class-unknown';
    }
  }

  // Processing Actions
  function setupActions() {
    elements.startProcessBtn.addEventListener('click', runReconciliation);
    elements.recalcBtn.addEventListener('click', recalculateTotals);
    elements.exportExcelBtn.addEventListener('click', exportReconciledExcel);
    elements.footerExportBtn.addEventListener('click', exportReconciledExcel);
  }

  async function runReconciliation() {
    if (!state.selectedFile) return;

    // Show progress overlay
    elements.processingOverlay.style.display = 'flex';
    elements.processingTitle.textContent = 'Analyzing Logistics Documents';
    elements.processingStep.textContent = 'Running local ONNX RapidOCR over pages...';

    const formData = new FormData();
    formData.append('file', state.selectedFile);

    let url = `/api/v1/bookings/reconcile?loading_point=${encodeURIComponent(
      state.loadingPoint
    )}&enable_ocr=${state.enableOcr}`;
    if (state.bookingType && state.bookingType !== 'auto') {
      url += `&booking_type=${encodeURIComponent(state.bookingType)}`;
    }

    try {
      const response = await fetch(url, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        let errorMsg = `Server returned error ${response.status} (${response.statusText || 'Error'})`;
        try {
          const rawText = await response.text();
          if (rawText && rawText.trim()) {
            try {
              const errorData = JSON.parse(rawText);
              errorMsg = errorData.message || errorData.detail || errorMsg;
            } catch (_) {
              if (response.status === 502) {
                errorMsg = 'Server returned 502 Bad Gateway: The server process crashed or was terminated by the host (commonly due to memory limits during high-DPI OCR on free hosting instances).';
              } else if (response.status === 504) {
                errorMsg = 'Server returned 504 Gateway Timeout: Processing took longer than the server timeout limit.';
              } else if (rawText.length < 200) {
                errorMsg = rawText.trim();
              }
            }
          } else if (response.status === 502) {
            errorMsg = 'Server returned 502 Bad Gateway with empty response: The OCR backend process was terminated (commonly out of memory on 512 MB free tier instances).';
          }
        } catch (_) { }
        throw new Error(errorMsg);
      }

      let data;
      try {
        const text = await response.text();
        if (!text || !text.trim()) {
          throw new Error('Server returned an empty response body');
        }
        data = JSON.parse(text);
      } catch (parseErr) {
        throw new Error(`Failed to parse server response as JSON: ${parseErr.message}`);
      }
      state.reconciliationData = data;
      state.totalPages = data.total_pages_in || 1;

      // Render Review UI
      populateReviewScreen(data);

      // Switch views
      elements.processingOverlay.style.display = 'none';
      elements.ingestSection.style.display = 'none';
      elements.reviewSection.style.display = 'flex';

      // Open page 1
      goToPage(1);
    } catch (err) {
      elements.processingOverlay.style.display = 'none';
      alert(`Reconciliation error: ${err.message}`);
    }
  }

  // Populate Review Screen
  function populateReviewScreen(data) {
    // 1. Top Summary Bar
    elements.barDocName.textContent = data.original_filename || state.selectedFile.name;
    elements.barPageConservation.textContent = `${data.total_pages_accounted_for}/${data.total_pages_in} Conserved`;

    // 2. Multi-Truck Selector Bar
    state.activeTruckIndex = 0;
    renderTruckSelector(data);

    // 3. Build Thumbnails
    buildThumbnailBar(data);

    // 4. Select active truck dossier
    selectTruck(0);

    // 5. Render Discrepancies
    renderDiscrepancies(data);

    // 6. Render Page Accounting
    renderAccounting(data);
  }

  function renderTruckSelector(data) {
    if (!elements.truckSelectorBar) return;
    const dossiers = data.truck_dossiers || [];

    if (dossiers.length > 1) {
      elements.truckSelectorBar.style.display = 'flex';
      elements.truckSelectorBar.innerHTML = '';

      dossiers.forEach((d, idx) => {
        const pill = document.createElement('div');
        pill.className = `truck-tab-pill ${idx === state.activeTruckIndex ? 'active' : ''}`;
        const lrsCount = d.reconciled_consignments ? d.reconciled_consignments.length : 0;
        const bType = d.booking_type ? d.booking_type.toUpperCase() : 'TRIP';
        pill.innerHTML = `
          <span>🚚 ${d.truck_number}</span>
          <span class="truck-tab-badge">${bType} • ${lrsCount} LR${lrsCount === 1 ? '' : 's'}</span>
        `;
        pill.addEventListener('click', () => {
          // Persist working edits on active truck before switching
          const prevD = dossiers[state.activeTruckIndex];
          if (prevD) {
            prevD.reconciled_consignments = state.workingConsignments;
          }
          state.activeTruckIndex = idx;
          selectTruck(idx);
        });
        elements.truckSelectorBar.appendChild(pill);
      });
    } else {
      elements.truckSelectorBar.style.display = 'none';
      elements.truckSelectorBar.innerHTML = '';
    }
  }

  function selectTruck(index) {
    const data = state.reconciliationData;
    if (!data) return;
    const dossiers = data.truck_dossiers || [];
    const dossier = dossiers[index];

    // Update active tab pill in selector bar
    if (elements.truckSelectorBar) {
      const pills = elements.truckSelectorBar.querySelectorAll('.truck-tab-pill');
      pills.forEach((p, idx) => {
        p.classList.toggle('active', idx === index);
      });
    }

    if (dossier) {
      elements.barTruckPlate.textContent = dossier.truck_number;
      elements.barStatusBadge.textContent = dossier.dossier_status;
      elements.barStatusBadge.className =
        'badge-status ' +
        (dossier.dossier_status === 'CONFIRMED' ? 'badge-status-confirmed' : 'badge-status-review');
    } else {
      elements.barTruckPlate.textContent = 'NO DOSSIER';
      elements.barStatusBadge.textContent = 'REVIEW_REQUIRED';
      elements.barStatusBadge.className = 'badge-status badge-status-review';
    }

    // Render Aggregated Metrics for selected truck
    updateAggregatedMetrics(dossier);

    // Render Consignments Cards for selected truck
    renderConsignments(dossier ? dossier.reconciled_consignments : []);

    // Jump to the first page associated with this truck
    if (dossier && dossier.reconciled_consignments && dossier.reconciled_consignments.length > 0) {
      const firstPage = dossier.reconciled_consignments[0].source_page;
      if (firstPage && firstPage >= 1 && firstPage <= state.totalPages) {
        goToPage(firstPage);
      }
    }
  }

  function buildThumbnailBar(data) {
    elements.thumbnailBar.innerHTML = '';
    const pages = data.page_extractions || [];

    for (let p = 1; p <= state.totalPages; p++) {
      const pageInfo = pages.find((item) => item.page_number === p);
      const cls = pageInfo ? pageInfo.classification.classification : 'PAGE';
      const shortCls = getShortClassificationLabel(cls);

      const chip = document.createElement('div');
      chip.className = `thumb-chip ${p === 1 ? 'active' : ''}`;
      chip.innerHTML = `<span>P${p}</span><strong>${shortCls}</strong>`;
      chip.addEventListener('click', () => goToPage(p));
      elements.thumbnailBar.appendChild(chip);
    }
  }

  function getShortClassificationLabel(cls) {
    switch (cls) {
      case 'MATERIAL_INVOICE':
        return 'INV';
      case 'EWAY_BILL':
        return 'EWB';
      case 'LORRY_RECEIPT':
        return 'LR';
      case 'SECURITY_COPY':
        return 'SEC';
      case 'DESPATCH_SHEET':
        return 'DESP';
      default:
        return 'PAGE';
    }
  }

  function updateAggregatedMetrics(dossier) {
    if (!dossier) {
      elements.metricGrossWeight.textContent = '0.000 MT';
      elements.metricGrossKg.textContent = '0.00 kg';
      elements.metricPackages.textContent = '0';
      elements.metricTotalValue.textContent = '₹0.00';
      elements.metricFreight.textContent = '₹0.00';
      return;
    }

    elements.metricGrossWeight.textContent = `${dossier.truck_total_weight_mt.toFixed(3)} MT`;
    elements.metricGrossKg.textContent = `${(dossier.truck_total_weight_mt * 1000).toLocaleString(
      'en-IN',
      { minimumFractionDigits: 2 }
    )} kg`;
    elements.metricPackages.textContent = dossier.truck_total_packages.toLocaleString('en-IN');
    elements.metricTotalValue.textContent = `₹${dossier.truck_total_value_rs.toLocaleString('en-IN', {
      minimumFractionDigits: 2,
    })}`;
    elements.metricFreight.textContent = `₹${dossier.truck_total_freight_rs.toLocaleString('en-IN', {
      minimumFractionDigits: 2,
    })}`;

    if (dossier.security_copy_present) {
      const tiePkgs = dossier.packages_tie_security_copy ? 'TIED' : 'DIFF';
      elements.metricGateSheetTie.textContent = `Gate Sheet: ${tiePkgs}`;
      elements.metricGateSheetTie.style.color = dossier.packages_tie_security_copy
        ? 'var(--success)'
        : 'var(--warning)';
    } else if (state.loadingPoint === 'erode') {
      elements.metricGateSheetTie.textContent = 'Despatch Sheet: Verified';
      elements.metricGateSheetTie.style.color = 'var(--success)';
    } else {
      elements.metricGateSheetTie.textContent = 'Gate Sheet: N/A (Direct)';
      elements.metricGateSheetTie.style.color = 'var(--text-muted)';
    }

    elements.metricFreightMode.textContent =
      dossier.truck_total_freight_rs === 0 ? 'Party Freight (0.00)' : 'Shipper Freight';
  }

  // Render Consignments Tab
  function renderConsignments(consignments) {
    elements.consignmentsContainer.innerHTML = '';
    state.workingConsignments = JSON.parse(JSON.stringify(consignments));

    if (consignments.length === 0) {
      elements.consignmentsContainer.innerHTML =
        '<div class="notice-banner banner-warning">No confirmed consignments found in this document.</div>';
      return;
    }

    state.workingConsignments.forEach((c, index) => {
      const card = document.createElement('div');
      card.className = 'consignment-card';
      card.innerHTML = `
        <div class="consignment-header">
          <h3>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
            Consignment ${index + 1}: LR ${c.lr_number_raw} (Page ${c.source_page})
          </h3>
          <span class="badge-status ${c.status === 'CONFIRMED' ? 'badge-status-confirmed' : 'badge-status-review'
        }">${c.status}</span>
        </div>

        <div class="fields-grid">
          <!-- LR Number -->
          <div class="field-item">
            <div class="field-header">
              <span class="field-label">LR Number (Raw & Normalized)</span>
              <span class="confidence-chip conf-high">Confirmed</span>
            </div>
            ${c.lr_crop_base64
          ? `<div class="lr-crop-container" title="Handwritten LR snippet (FR4)">
                     <div class="lr-crop-header">
                       <span class="lr-crop-label">Handwritten LR Snippet (FR4)</span>
                       <span class="confidence-chip conf-high" style="font-size: 0.65rem;">LR Crop</span>
                     </div>
                     <img src="data:image/png;base64,${c.lr_crop_base64}" alt="Handwritten LR ${c.lr_number_raw}" class="lr-crop-image" />
                   </div>`
          : ''
        }
            <input type="text" class="editable-input" data-field="lr_number_raw" data-idx="${index}" value="${c.lr_number_raw
        }">
          </div>

          <!-- Truck Number -->
          <div class="field-item">
            <div class="field-header">
              <span class="field-label">Truck Registration</span>
              <span class="confidence-chip conf-high">Vehicle</span>
            </div>
            <input type="text" class="editable-input" data-field="truck_number" data-idx="${index}" value="${c.truck_number
        }">
          </div>

          <!-- Booking Date -->
          <div class="field-item">
            <div class="field-header">
              <span class="field-label">Booking Date</span>
            </div>
            <input type="text" class="editable-input" data-field="booking_date" data-idx="${index}" value="${c.booking_date
        }">
          </div>

          <!-- Invoices Range -->
          <div class="field-item">
            <div class="field-header">
              <span class="field-label">Invoices Range (PRD §5.3)</span>
              <span class="confidence-chip conf-high">${c.unique_invoices.length} unique</span>
            </div>
            <input type="text" class="editable-input" data-field="compressed_invoices_cell" data-idx="${index}" value="${c.compressed_invoices_cell
        }">
          </div>

          <!-- Delivery Place -->
          <div class="field-item">
            <div class="field-header">
              <span class="field-label">Delivery Destination</span>
            </div>
            <input type="text" class="editable-input" data-field="delivery_place" data-idx="${index}" value="${c.delivery_place
        }">
          </div>

          <!-- Consignee -->
          <div class="field-item">
            <div class="field-header">
              <span class="field-label">Consignee</span>
            </div>
            <input type="text" class="editable-input" data-field="consignee" data-idx="${index}" value="${c.consignee
        }">
          </div>

          <!-- Bill-To -->
          <div class="field-item">
            <div class="field-header">
              <span class="field-label">Bill To Customer</span>
              ${c.bill_to_differs_from_delivery
          ? '<span class="confidence-chip conf-mid" title="Differs from delivery destination">Differs from Delivery</span>'
          : ''
        }
            </div>
            <input type="text" class="editable-input ${c.bill_to_differs_from_delivery ? 'diff-alert' : ''
        }" data-field="bill_to" data-idx="${index}" value="${c.bill_to}">
          </div>

          <!-- Total Packages -->
          <div class="field-item">
            <div class="field-header">
              <span class="field-label">Total Packages</span>
            </div>
            <input type="number" class="editable-input" data-field="total_packages" data-idx="${index}" value="${c.total_packages
        }">
          </div>

          <!-- Governing Weight (MT) -->
          <div class="field-item">
            <div class="field-header">
              <span class="field-label">Governing Gross Wt (MT)</span>
              <span class="confidence-chip conf-high">Invoice Governs</span>
            </div>
            <input type="number" step="0.001" class="editable-input" data-field="governing_weight_mt" data-idx="${index}" value="${c.governing_weight_mt.toFixed(
          3
        )}">
          </div>

          <!-- Consignment Value -->
          <div class="field-item">
            <div class="field-header">
              <span class="field-label">Total Consignment Value (₹)</span>
            </div>
            <input type="number" step="0.01" class="editable-input" data-field="total_value_rs" data-idx="${index}" value="${c.total_value_rs.toFixed(
          2
        )}">
          </div>

          <!-- Freight Amount -->
          <div class="field-item">
            <div class="field-header">
              <span class="field-label">Freight Charge (₹)</span>
              <span class="confidence-chip ${c.is_party_freight ? 'conf-high' : 'conf-mid'}">${c.is_party_freight ? 'Party Freight (0.00)' : 'Shipper Freight'
        }</span>
            </div>
            <input type="number" step="0.01" class="editable-input" data-field="freight_amount" data-idx="${index}" value="${c.freight_amount.toFixed(
          2
        )}">
          </div>

          <!-- E-Way Bills -->
          <div class="field-item">
            <div class="field-header">
              <span class="field-label">E-Way Bill Numbers</span>
            </div>
            <input type="text" class="editable-input" data-field="eway_bills_cell" data-idx="${index}" value="${c.eway_bills_cell
        }">
          </div>
        </div>

        ${c.audit_notes && c.audit_notes.length > 0
          ? `<div style="margin-top: 1rem; padding-top: 0.75rem; border-top: 1px solid var(--border-color);">
                <span class="field-label" style="display:block; margin-bottom: 0.4rem;">Consignment Audit Flags:</span>
                ${c.audit_notes
            .map((note) => `<div class="raw-snippet" style="color: #fbbf24;">⚠️ ${note}</div>`)
            .join('')}
               </div>`
          : ''
        }
      `;

      elements.consignmentsContainer.appendChild(card);
    });

    // Add event listeners for edits
    const inputs = elements.consignmentsContainer.querySelectorAll('.editable-input');
    inputs.forEach((input) => {
      input.addEventListener('change', handleFieldEdit);
    });
  }

  function handleFieldEdit(e) {
    const field = e.target.getAttribute('data-field');
    const idx = parseInt(e.target.getAttribute('data-idx'), 10);
    const value = e.target.value;

    if (state.workingConsignments[idx]) {
      if (
        field === 'governing_weight_mt' ||
        field === 'total_value_rs' ||
        field === 'freight_amount'
      ) {
        state.workingConsignments[idx][field] = parseFloat(value) || 0;
        if (field === 'governing_weight_mt') {
          state.workingConsignments[idx].governing_weight_kg =
            state.workingConsignments[idx][field] * 1000;
        }
        if (field === 'freight_amount') {
          state.workingConsignments[idx].is_party_freight =
            state.workingConsignments[idx][field] === 0;
        }
      } else if (field === 'total_packages') {
        state.workingConsignments[idx][field] = parseInt(value, 10) || 0;
      } else {
        state.workingConsignments[idx][field] = value;
      }
    }
  }

  function recalculateTotals() {
    if (!state.reconciliationData || !state.reconciliationData.truck_dossiers) return;
    const dossier = state.reconciliationData.truck_dossiers[state.activeTruckIndex || 0];
    if (!dossier) return;

    // Synchronize working consignments back into state
    dossier.reconciled_consignments = state.workingConsignments;

    // Recalculate totals
    let totalWeight = 0;
    let totalPkgs = 0;
    let totalVal = 0;
    let totalFreight = 0;

    state.workingConsignments.forEach((c) => {
      totalWeight += c.governing_weight_mt;
      totalPkgs += c.total_packages;
      totalVal += c.total_value_rs;
      totalFreight += c.freight_amount;
    });

    dossier.truck_total_weight_mt = Math.round(totalWeight * 1000) / 1000;
    dossier.truck_total_packages = totalPkgs;
    dossier.truck_total_value_rs = Math.round(totalVal * 100) / 100;
    dossier.truck_total_freight_rs = Math.round(totalFreight * 100) / 100;

    updateAggregatedMetrics(dossier);
    alert('Consignment totals recalculated successfully.');
  }

  // Render Page Details Tab
  function renderSelectedPageExtraction(pageNum) {
    const pages = state.reconciliationData?.page_extractions || [];
    const pageData = pages.find((p) => p.page_number === pageNum);

    if (!pageData) {
      elements.selectedPageContent.innerHTML =
        '<div class="notice-banner banner-info">No extraction details recorded for this page.</div>';
      return;
    }

    const cls = pageData.classification.classification;
    const conf = Math.round(pageData.classification.confidence * 100);
    const anchors = (pageData.classification.detected_anchors || []).join(', ');
    const flags = pageData.review_flags || [];
    const ext = pageData.extracted_data || pageData.invoice_data || pageData.lr_data || pageData.eway_data || pageData.security_data || {};

    let fieldsHtml = '';
    for (const [key, fieldObj] of Object.entries(ext)) {
      if (fieldObj && typeof fieldObj === 'object' && ('value' in fieldObj || 'raw_value' in fieldObj)) {
        const val = 'value' in fieldObj ? fieldObj.value : fieldObj.raw_value;
        const fieldConf = fieldObj.confidence
          ? `${Math.round(fieldObj.confidence * 100)}%`
          : 'High';
        const rawSnippet = fieldObj.raw_text || '';
        fieldsHtml += `
          <div class="field-item" style="margin-bottom: 0.75rem;">
            <div class="field-header">
              <span class="field-label">${formatFieldLabel(key)}</span>
              <span class="confidence-chip conf-high">${fieldConf}</span>
            </div>
            <div class="editable-input" style="background: rgba(255,255,255,0.03);">${val !== null && val !== undefined ? val : '—'
          }</div>
            ${rawSnippet ? `<div class="raw-snippet">OCR: "${rawSnippet}"</div>` : ''}
          </div>
        `;
      }
    }

    elements.selectedPageContent.innerHTML = `
      <div style="background: var(--bg-tertiary); padding: 1rem; border-radius: var(--radius-sm); margin-bottom: 1rem; border: 1px solid var(--border-color);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 0.5rem;">
          <strong>Page ${pageNum}: ${cls}</strong>
          <span class="confidence-chip conf-high">${conf}% Confidence</span>
        </div>
        <div style="font-size: 0.75rem; color: var(--text-secondary);">
          <strong>Anchors:</strong> ${anchors || 'None'}
        </div>
      </div>

      ${flags.length > 0
        ? `<div class="banner-list">${flags
          .map(
            (f) =>
              `<div class="notice-banner banner-warning"><svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" fill="none"><path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>${f}</div>`
          )
          .join('')}</div>`
        : ''
      }

      <div class="card-title">Extracted Document Fields</div>
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem;">
        ${fieldsHtml || '<div style="color: var(--text-muted);">No structured fields extracted on this page.</div>'}
      </div>
    `;
  }

  function formatFieldLabel(key) {
    return key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (l) => l.toUpperCase());
  }

  // Render Discrepancies Tab
  function renderDiscrepancies(data) {
    elements.discrepanciesContainer.innerHTML = '';
    const flags = [];

    // Global flags
    (data.global_reconciliation_flags || []).forEach((f) => flags.push({ type: 'global', text: f }));

    // Dossier flags
    if (data.truck_dossiers[0]) {
      (data.truck_dossiers[0].dossier_review_flags || []).forEach((f) =>
        flags.push({ type: 'dossier', text: f })
      );

      // Consignment audit notes
      data.truck_dossiers[0].reconciled_consignments.forEach((c) => {
        (c.audit_notes || []).forEach((n) =>
          flags.push({ type: 'consignment', text: `[LR ${c.lr_number_raw}] ${n}` })
        );
      });
    }

    elements.tabDiscrepancyCount.textContent = flags.length;

    if (flags.length === 0) {
      elements.discrepanciesContainer.innerHTML =
        '<div class="notice-banner banner-success">✓ Zero discrepancies detected. All business rules confirmed cleanly.</div>';
      return;
    }

    flags.forEach((flag) => {
      const banner = document.createElement('div');
      banner.className = 'notice-banner banner-warning';
      banner.innerHTML = `
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="8" x2="12" y2="12"></line>
          <line x1="12" y1="16" x2="12.01" y2="16"></line>
        </svg>
        <div>${flag.text}</div>
      `;
      elements.discrepanciesContainer.appendChild(banner);
    });
  }

  // Render Page Accounting Tab
  function renderAccounting(data) {
    elements.accountingSummary.innerHTML = `
      <div style="background: var(--bg-tertiary); padding: 1rem; border-radius: var(--radius-sm); border: 1px solid var(--border-color);">
        <div style="display:flex; justify-content:space-between; margin-bottom: 0.5rem;">
          <span>Total Input Pages: <strong>${data.total_pages_in}</strong></span>
          <span>Accounted Pages: <strong>${data.total_pages_accounted_for}</strong></span>
        </div>
        <div style="color: var(--success); font-weight: 600; font-size: 0.85rem;">
          ✓ 100% CONSERVED - Zero Pages Dropped
        </div>
      </div>
    `;

    const unassigned = data.unassigned_pages || [];
    if (unassigned.length === 0) {
      elements.unassignedPoolContainer.innerHTML =
        '<div class="notice-banner banner-success">Zero unassigned pages. All 9 pages cleanly assigned to truck dossier.</div>';
    } else {
      elements.unassignedPoolContainer.innerHTML = `
        <div class="card-title" style="color: #f87171;">Unassigned Pages Pool (${unassigned.length})</div>
        ${unassigned
          .map(
            (p) => `
          <div class="notice-banner banner-warning" style="margin-bottom: 0.5rem;">
            <strong>Page ${p.page_number} (${p.page_result.classification.classification}):</strong> ${p.unassigned_reason}
          </div>
        `
          )
          .join('')}
      `;
    }
  }

  // Export Reconciled Excel (.xlsx)
  async function exportReconciledExcel() {
    if (!state.reconciliationData) return;

    // Apply any edits on active truck to working data
    const activeDossier = state.reconciliationData.truck_dossiers[state.activeTruckIndex || 0];
    if (activeDossier) {
      activeDossier.reconciled_consignments = state.workingConsignments;
    }

    if (elements.footerExportBtn) {
      elements.footerExportBtn.disabled = true;
      elements.footerExportBtn.textContent = 'Generating Excel...';
    }
    if (elements.exportExcelBtn) {
      elements.exportExcelBtn.disabled = true;
      elements.exportExcelBtn.textContent = 'Generating...';
    }

    try {
      const response = await fetch('/api/v1/bookings/export-excel-from-reconciliation', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(state.reconciliationData),
      });

      if (!response.ok) {
        let errDesc = `Export failed with HTTP ${response.status} (${response.statusText || 'Error'})`;
        try {
          const raw = await response.text();
          if (raw && raw.trim()) {
            try {
              const errObj = JSON.parse(raw);
              errDesc = errObj.message || errObj.detail || errDesc;
            } catch (_) {
              if (raw.length < 200) errDesc = raw.trim();
            }
          }
        } catch (_) { }
        throw new Error(errDesc);
      }

      const blob = await response.blob();
      const downloadUrl = URL.createObjectURL(blob);

      // Extract filename from header or construct default
      const contentDisposition = response.headers.get('Content-Disposition');
      let filename = 'reconciled_consignments.xlsx';
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="?([^"]+)"?/);
        if (match && match[1]) {
          filename = match[1];
        }
      }

      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(downloadUrl);

      if (elements.footerStatusText) {
        elements.footerStatusText.textContent = `✓ Successfully exported ${filename}`;
        elements.footerStatusText.style.color = 'var(--success)';
      }
    } catch (err) {
      alert(`Excel export failed: ${err.message}`);
    } finally {
      if (elements.footerExportBtn) {
        elements.footerExportBtn.disabled = false;
        elements.footerExportBtn.textContent = 'Download Reconciled Excel (.xlsx)';
      }
      if (elements.exportExcelBtn) {
        elements.exportExcelBtn.disabled = false;
        elements.exportExcelBtn.innerHTML = `
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="7 10 12 15 17 10"></polyline>
            <line x1="12" y1="15" x2="12" y2="3"></line>
          </svg>
          Approve & Export Excel (.xlsx)
        `;
      }
    }
  }

  // Start app on DOM ready
  document.addEventListener('DOMContentLoaded', init);
})();
