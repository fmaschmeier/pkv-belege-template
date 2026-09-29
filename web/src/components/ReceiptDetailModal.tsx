import { useState, useRef, useEffect, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Document, Page } from 'react-pdf'
import { receiptsApi, rulesApi } from '../lib/api'
import type { Receipt, ProviderPaymentInfo } from '../lib/api'
import { formatDate, formatCurrency } from '../lib/utils'
import { X, Upload, FileText, ExternalLink, Loader2, Pencil, Save, XCircle, ZoomIn, ChevronLeft, ChevronRight, RefreshCw, Trash2 } from 'lucide-react'
import PdfZoomModal from './PdfZoomModal'
import '../lib/pdfConfig'

interface ReceiptDetailModalProps {
  receipt: Receipt
  onClose: () => void
}

export default function ReceiptDetailModal({
  receipt,
  onClose,
}: ReceiptDetailModalProps) {
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [currentReceipt, setCurrentReceipt] = useState(receipt)
  const [pdfSignedUrl, setPdfSignedUrl] = useState<string | null>(null)
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null)
  const [loadingPdf, setLoadingPdf] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editValues, setEditValues] = useState<Partial<Receipt>>({})
  const [showZoomModal, setShowZoomModal] = useState(false)
  const [numPages, setNumPages] = useState<number>(1)
  const [currentPage, setCurrentPage] = useState<number>(1)
  const [isHoveringPdf, setIsHoveringPdf] = useState(false)
  const [zoomPosition, setZoomPosition] = useState({ x: 0.5, y: 0.5 })
  const [zoomScale, setZoomScale] = useState(3)
  const [providerPaymentInfoList, setProviderPaymentInfoList] = useState<ProviderPaymentInfo[]>([])
  const [showSaveIbanDialog, setShowSaveIbanDialog] = useState(false)
  const [pendingIbanSave, setPendingIbanSave] = useState<{ recipient: string; iban: string } | null>(null)
  const [showRecipientSuggestions, setShowRecipientSuggestions] = useState(false)
  const [recipientSuggestions, setRecipientSuggestions] = useState<ProviderPaymentInfo[]>([])
  const [reparsing, setReparsing] = useState(false)
  const [deletingPdf, setDeletingPdf] = useState(false)
  const [showDeletePdfConfirm, setShowDeletePdfConfirm] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pdfContainerRef = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()

  // Format IBAN with spaces every 4 characters
  const formatIban = (iban: string | null | undefined): string => {
    if (!iban) return ''
    const cleaned = iban.replace(/\s/g, '').toUpperCase()
    return cleaned.match(/.{1,4}/g)?.join(' ') || cleaned
  }

  // Remove spaces from IBAN for storage
  const cleanIban = (iban: string): string => {
    return iban.replace(/\s/g, '').toUpperCase()
  }

  // Generate auto-reference from invoice number and date
  const generateAutoReference = useCallback((): string => {
    if (currentReceipt.invoice_number && currentReceipt.invoice_date) {
      return `Rechnung Nr. ${currentReceipt.invoice_number} vom ${formatDate(currentReceipt.invoice_date)}`
    } else if (currentReceipt.invoice_number) {
      return `Rechnung Nr. ${currentReceipt.invoice_number}`
    } else if (currentReceipt.invoice_date) {
      return `Rechnung vom ${formatDate(currentReceipt.invoice_date)}`
    }
    return ''
  }, [currentReceipt.invoice_number, currentReceipt.invoice_date])

  // Load provider payment info list
  useEffect(() => {
    const loadProviderPaymentInfo = async () => {
      try {
        const result = await rulesApi.listPaymentInfo(true) // active only
        setProviderPaymentInfoList(result.items)
      } catch (err) {
        console.error('Failed to load provider payment info:', err)
      }
    }
    loadProviderPaymentInfo()
  }, [])

  // Find matching provider payment info by recipient/provider name
  // Matches if saved provider_pattern is found within the search text (case-insensitive)
  const findMatchingPaymentInfo = useCallback((searchText: string): ProviderPaymentInfo | undefined => {
    if (!searchText) return undefined
    const searchLower = searchText.toLowerCase()
    return providerPaymentInfoList.find(info => {
      const pattern = info.provider_pattern.toLowerCase()
      // Match if saved pattern is found within the provider name
      return searchLower.includes(pattern)
    })
  }, [providerPaymentInfoList])

  // Handle recipient change - show suggestions and auto-fill IBAN if matching provider found
  const handleRecipientChange = (newRecipient: string) => {
    setEditValues(prev => ({ ...prev, payment_recipient: newRecipient }))

    // Filter suggestions based on input (min 2 characters)
    if (newRecipient.length >= 2) {
      const inputLower = newRecipient.toLowerCase()
      const matches = providerPaymentInfoList.filter(info => {
        const pattern = info.provider_pattern.toLowerCase()
        const recipient = (info.payment_recipient || '').toLowerCase()
        // Match if input is found in pattern or recipient, or pattern/recipient is found in input
        return pattern.includes(inputLower) || recipient.includes(inputLower) ||
               inputLower.includes(pattern) || inputLower.includes(recipient)
      })
      setRecipientSuggestions(matches)
      setShowRecipientSuggestions(matches.length > 0)
    } else {
      setRecipientSuggestions([])
      setShowRecipientSuggestions(false)
    }
  }

  // Select a suggestion from the dropdown
  const selectRecipientSuggestion = (info: ProviderPaymentInfo) => {
    setEditValues(prev => ({
      ...prev,
      payment_recipient: info.payment_recipient || info.provider_pattern,
      payment_iban: info.payment_iban || '',
    }))
    setShowRecipientSuggestions(false)
    setRecipientSuggestions([])
  }

  // Handle IBAN change - check if we should offer to save it
  const handleIbanChange = (newIban: string) => {
    const cleanedIban = cleanIban(newIban)
    setEditValues(prev => ({ ...prev, payment_iban: cleanedIban }))
  }

  // Check if IBAN should be saved when leaving edit mode
  const checkSaveIban = (): boolean => {
    const recipient = editValues.payment_recipient || currentReceipt.provider_name || ''
    const iban = editValues.payment_iban || ''

    if (!recipient || !iban || iban.length < 15) return false

    const recipientLower = recipient.toLowerCase()

    // Check if this recipient/iban combo is already saved
    // Match if saved pattern is found within the recipient name
    const existingMatch = providerPaymentInfoList.find(info => {
      const patternLower = info.provider_pattern.toLowerCase()
      return recipientLower.includes(patternLower) && info.payment_iban === iban
    })

    if (existingMatch) return false // Already saved

    // Check if we have this recipient but with different IBAN
    const recipientMatch = providerPaymentInfoList.find(info => {
      const patternLower = info.provider_pattern.toLowerCase()
      return recipientLower.includes(patternLower)
    })

    // Offer to save if: new recipient, or existing recipient with different IBAN
    return !recipientMatch || recipientMatch.payment_iban !== iban
  }

  // Save IBAN to provider payment info
  const saveIbanToProvider = async () => {
    if (!pendingIbanSave) return

    try {
      await rulesApi.createPaymentInfo({
        provider_pattern: pendingIbanSave.recipient,
        payment_recipient: pendingIbanSave.recipient,
        payment_iban: pendingIbanSave.iban,
        active: true,
      })
      // Refresh list
      const result = await rulesApi.listPaymentInfo(true)
      setProviderPaymentInfoList(result.items)
      setMessage({ type: 'success', text: 'Bankverbindung gespeichert' })
    } catch (err) {
      console.error('Failed to save payment info:', err)
    }
    setShowSaveIbanDialog(false)
    setPendingIbanSave(null)
  }

  // Re-parse PDF with Claude Vision
  const handleReparse = async () => {
    if (!currentReceipt.pdf_url) {
      setMessage({ type: 'error', text: 'Kein PDF vorhanden' })
      return
    }

    setReparsing(true)
    setMessage(null)

    try {
      const result = await receiptsApi.reparse(currentReceipt.id)
      setMessage({ type: 'success', text: result.message })
      // Update local state with full updated receipt data
      if (result.receipt) {
        setCurrentReceipt(result.receipt)
      } else {
        // Fallback: only update parsed_params if full receipt not returned
        setCurrentReceipt(prev => ({
          ...prev,
          parsed_params: result.parsed_params,
        }))
      }
      queryClient.invalidateQueries({ queryKey: ['receipts'] })
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Parsing fehlgeschlagen',
      })
    } finally {
      setReparsing(false)
    }
  }

  // Delete PDF and reset related fields
  const handleDeletePdf = async () => {
    setDeletingPdf(true)
    setMessage(null)

    try {
      const result = await receiptsApi.deletePdf(currentReceipt.id)
      setMessage({ type: 'success', text: result.message })
      // Update local state - clear PDF-related fields
      setCurrentReceipt(prev => ({
        ...prev,
        pdf_url: null,
        pdf_filename: '',
        pdf_hash: '',
        parsed_params: null,
      }))
      // Clear PDF display state
      setPdfSignedUrl(null)
      setPdfBlobUrl(null)
      queryClient.invalidateQueries({ queryKey: ['receipts'] })
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Löschen fehlgeschlagen',
      })
    } finally {
      setDeletingPdf(false)
      setShowDeletePdfConfirm(false)
    }
  }

  const receiptTypes = [
    { value: 'arzt', label: 'Arzt' },
    { value: 'rezept', label: 'Rezept' },
    { value: 'pflege', label: 'Pflege' },
    { value: 'hilfsmittel', label: 'Hilfsmittel' },
    { value: 'sonstige', label: 'Sonstige' },
  ]

  const startEditing = () => {
    setIsEditing(true)

    // Check if we should auto-fill payment info based on provider_name
    let autoIban = currentReceipt.payment_iban || ''
    let autoRecipient = currentReceipt.payment_recipient || ''

    // If no IBAN yet, try to find matching payment info from provider_name
    if (!autoIban && currentReceipt.provider_name) {
      const match = findMatchingPaymentInfo(currentReceipt.provider_name)
      if (match) {
        autoIban = match.payment_iban || ''
        if (!autoRecipient && match.payment_recipient) {
          autoRecipient = match.payment_recipient
        }
      }
    }

    setEditValues({
      provider_name: currentReceipt.provider_name || '',
      invoice_amount: currentReceipt.invoice_amount,
      invoice_date: currentReceipt.invoice_date || '',
      invoice_number: currentReceipt.invoice_number || '',
      insured_person: currentReceipt.insured_person || '',
      receipt_type: currentReceipt.receipt_type || 'sonstige',
      description: currentReceipt.description || '',
      submission_date: currentReceipt.submission_date || '',
      due_date: currentReceipt.due_date || '',
      payment_recipient: autoRecipient,
      payment_iban: autoIban,
      payment_reference: currentReceipt.payment_reference || '',
    })
  }

  const cancelEditing = () => {
    setIsEditing(false)
    setEditValues({})
  }

  const handleClose = () => {
    if (isEditing) {
      if (window.confirm('Du hast ungespeicherte Änderungen. Wirklich schließen?')) {
        setIsEditing(false)
        setEditValues({})
        onClose()
      }
    } else {
      onClose()
    }
  }

  const saveEditing = async () => {
    try {
      // Build update object with only changed values
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const updates: Record<string, any> = {}
      if (editValues.provider_name !== (currentReceipt.provider_name || '')) {
        updates.provider_name = editValues.provider_name || null
      }
      if (editValues.invoice_amount !== currentReceipt.invoice_amount) {
        updates.invoice_amount = editValues.invoice_amount
      }
      if (editValues.invoice_date !== (currentReceipt.invoice_date || '')) {
        updates.invoice_date = editValues.invoice_date || null
      }
      if (editValues.invoice_number !== (currentReceipt.invoice_number || '')) {
        updates.invoice_number = editValues.invoice_number || null
      }
      if (editValues.insured_person !== (currentReceipt.insured_person || '')) {
        updates.insured_person = editValues.insured_person || null
      }
      if (editValues.receipt_type !== (currentReceipt.receipt_type || 'sonstige')) {
        updates.receipt_type = editValues.receipt_type
      }
      if (editValues.description !== (currentReceipt.description || '')) {
        updates.description = editValues.description || null
      }
      if (editValues.submission_date !== (currentReceipt.submission_date || '')) {
        updates.submission_date = editValues.submission_date || null
      }
      if (editValues.due_date !== (currentReceipt.due_date || '')) {
        updates.due_date = editValues.due_date || null
      }
      if (editValues.payment_recipient !== (currentReceipt.payment_recipient || '')) {
        updates.payment_recipient = editValues.payment_recipient || null
      }
      if (editValues.payment_iban !== (currentReceipt.payment_iban || '')) {
        updates.payment_iban = editValues.payment_iban || null
      }
      if (editValues.payment_reference !== (currentReceipt.payment_reference || '')) {
        updates.payment_reference = editValues.payment_reference || null
      }

      if (Object.keys(updates).length === 0) {
        setIsEditing(false)
        return
      }

      await receiptsApi.update(currentReceipt.id, updates)
      setMessage({ type: 'success', text: 'Beleg aktualisiert' })
      // Update local state - only update the fields that were actually changed
      // Preserve parsed_params, raw_text, pdf_url and other non-editable fields
      setCurrentReceipt(prev => ({
        ...prev,
        ...updates,  // Only apply the actual changes, not all editValues
      }))
      queryClient.invalidateQueries({ queryKey: ['receipts'] })

      // Check if we should offer to save IBAN
      if (checkSaveIban()) {
        const recipient = editValues.payment_recipient || currentReceipt.provider_name || ''
        const iban = editValues.payment_iban || ''
        setPendingIbanSave({ recipient, iban })
        setShowSaveIbanDialog(true)
      }

      setIsEditing(false)
      setEditValues({})
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Speichern fehlgeschlagen',
      })
    }
  }

  // Load signed URL when modal opens (if pdf exists)
  useEffect(() => {
    if (receipt.pdf_url) {
      loadSignedUrl()
    }
  }, [receipt.id, receipt.pdf_url])

  const loadSignedUrl = async () => {
    setLoadingPdf(true)
    try {
      const result = await receiptsApi.getPdfUrl(receipt.id)
      setPdfSignedUrl(result.signed_url)

      // Fetch PDF as blob for react-pdf rendering
      const response = await fetch(result.signed_url)
      if (response.ok) {
        const blob = await response.blob()
        const blobUrl = URL.createObjectURL(blob)
        setPdfBlobUrl(blobUrl)
      }
    } catch (err) {
      console.error('Failed to load PDF URL:', err)
      setMessage({
        type: 'error',
        text: 'PDF-URL konnte nicht geladen werden',
      })
    } finally {
      setLoadingPdf(false)
    }
  }

  // Cleanup blob URL on unmount
  useEffect(() => {
    return () => {
      if (pdfBlobUrl) {
        URL.revokeObjectURL(pdfBlobUrl)
      }
    }
  }, [pdfBlobUrl])

  const handlePdfUpload = async (file: File) => {
    setUploading(true)
    setMessage(null)
    try {
      const result = await receiptsApi.uploadPdf(receipt.id, file)
      setMessage({ type: 'success', text: result.message })
      // Update local state with storage path and load signed URL
      setCurrentReceipt(prev => ({ ...prev, pdf_url: result.storage_path }))
      queryClient.invalidateQueries({ queryKey: ['receipts'] })
      // Load the signed URL for display
      await loadSignedUrl()
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Upload fehlgeschlagen',
      })
    } finally {
      setUploading(false)
    }
  }

  const statusColors: Record<string, string> = {
    submitted: 'bg-blue-100 text-blue-800',
    reimbursed: 'bg-green-100 text-green-800',
    rejected: 'bg-red-100 text-red-800',
    partial: 'bg-yellow-100 text-yellow-800',
  }

  const statusLabels: Record<string, string> = {
    submitted: 'Eingereicht',
    reimbursed: 'Erstattet',
    rejected: 'Abgelehnt',
    partial: 'Teilweise',
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        {/* Backdrop */}
        <div className="fixed inset-0 bg-black/50" onClick={handleClose} />

        {/* Modal - wider for 3 columns */}
        <div className="relative bg-white rounded-lg shadow-xl max-w-7xl w-full max-h-[90vh] overflow-hidden flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b bg-gray-50 rounded-t-lg">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">
                Beleg: {currentReceipt.provider_name || 'Unbekannt'}
              </h2>
              <p className="text-sm text-gray-500">
                Eingereicht: {formatDate(currentReceipt.submission_date)} |
                Betrag: {formatCurrency(currentReceipt.invoice_amount)} |
                <span className={`ml-2 px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[currentReceipt.status] || 'bg-gray-100 text-gray-800'}`}>
                  {statusLabels[currentReceipt.status] || currentReceipt.status}
                </span>
              </p>
            </div>
            <button onClick={handleClose} className="text-gray-400 hover:text-gray-600">
              <X className="h-6 w-6" />
            </button>
          </div>

          {/* Message */}
          {message && (
            <div className={`mx-6 mt-4 p-3 rounded-md ${message.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
              {message.text}
            </div>
          )}

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {/* PDF + Zoom + Parsed Parameters Section - 3 columns with custom widths */}
            <div className="grid grid-cols-1 lg:grid-cols-[200px_1fr_1.5fr] gap-4">
              {/* PDF Viewer - narrow */}
              <div className="border rounded-lg overflow-hidden">
                <div className="bg-gray-100 px-2 py-2 border-b flex items-center justify-between">
                  <span className="font-medium text-xs text-gray-700">PDF</span>
                  {/* Page Navigation */}
                  {pdfBlobUrl && numPages > 1 ? (
                    <div className="flex items-center gap-0.5">
                      <button
                        onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                        disabled={currentPage <= 1}
                        className="p-0.5 text-gray-500 hover:text-gray-700 disabled:opacity-30 disabled:cursor-not-allowed"
                        title="Vorherige Seite"
                      >
                        <ChevronLeft className="h-3 w-3" />
                      </button>
                      <span className="text-xs text-gray-600 min-w-[40px] text-center">
                        {currentPage}/{numPages}
                      </span>
                      <button
                        onClick={() => setCurrentPage(p => Math.min(numPages, p + 1))}
                        disabled={currentPage >= numPages}
                        className="p-0.5 text-gray-500 hover:text-gray-700 disabled:opacity-30 disabled:cursor-not-allowed"
                        title="Nächste Seite"
                      >
                        <ChevronRight className="h-3 w-3" />
                      </button>
                    </div>
                  ) : (
                    <div />
                  )}
                  {pdfSignedUrl && (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => setShowDeletePdfConfirm(true)}
                        className="text-red-500 hover:text-red-700 text-xs"
                        title="PDF entfernen"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                      <a
                        href={pdfSignedUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:text-blue-800 text-xs"
                        title="PDF öffnen"
                      >
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </div>
                  )}
                </div>
                {loadingPdf ? (
                  <div className="h-72 flex items-center justify-center bg-gray-50">
                    <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
                  </div>
                ) : pdfBlobUrl ? (
                  <div className="p-2 flex justify-center bg-gray-50">
                    {/* PDF Preview - narrow */}
                    <div
                      ref={pdfContainerRef}
                      className="relative cursor-pointer"
                      style={{ width: 170, height: 240, borderRadius: '4px', overflow: 'hidden', border: '1px solid #e5e7eb', backgroundColor: '#ffffff' }}
                      onMouseEnter={() => setIsHoveringPdf(true)}
                      onMouseLeave={() => setIsHoveringPdf(false)}
                      onMouseMove={(e) => {
                        if (pdfContainerRef.current) {
                          const rect = pdfContainerRef.current.getBoundingClientRect()
                          const x = (e.clientX - rect.left) / rect.width
                          const y = (e.clientY - rect.top) / rect.height
                          setZoomPosition({ x, y })
                        }
                      }}
                      onClick={() => setZoomScale(s => s === 3 ? 6 : 3)}
                    >
                      <Document
                        file={pdfBlobUrl}
                        onLoadSuccess={({ numPages: n }) => setNumPages(n)}
                        loading={
                          <div style={{ width: 170, height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f9fafb' }}>
                            <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
                          </div>
                        }
                        error={
                          <div style={{ width: 170, height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f9fafb', color: '#9ca3af' }}>
                            <FileText className="h-8 w-8" />
                          </div>
                        }
                      >
                        <Page
                          pageNumber={currentPage}
                          width={170}
                          renderTextLayer={false}
                          renderAnnotationLayer={false}
                        />
                      </Document>
                      {/* Hover indicator - size changes with zoom level */}
                      {isHoveringPdf && (() => {
                        // Indicator size inversely proportional to zoom: larger at 3x, smaller at 6x
                        const indicatorSize = Math.round(50 * (6 / zoomScale))
                        const halfSize = indicatorSize / 2
                        return (
                          <div
                            className="absolute pointer-events-none border-2 border-blue-500 rounded"
                            style={{
                              width: indicatorSize,
                              height: indicatorSize,
                              left: Math.max(0, Math.min(170 - indicatorSize, zoomPosition.x * 170 - halfSize)),
                              top: Math.max(0, Math.min(240 - indicatorSize, zoomPosition.y * 240 - halfSize)),
                              backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            }}
                          />
                        )
                      })()}
                    </div>
                  </div>
                ) : (
                  <div className="h-72 flex flex-col items-center justify-center bg-gray-50 text-gray-500">
                    <FileText className="h-8 w-8 mb-2 text-gray-300" />
                    <p className="mb-2 text-xs">Kein PDF</p>
                    <input
                      type="file"
                      ref={fileInputRef}
                      accept=".pdf"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0]
                        if (file) {
                          handlePdfUpload(file)
                          e.target.value = ''
                        }
                      }}
                    />
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      disabled={uploading}
                      className="flex items-center gap-1 px-2 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 disabled:opacity-50"
                    >
                      <Upload className={`h-3 w-3 ${uploading ? 'animate-pulse' : ''}`} />
                      {uploading ? '...' : 'Upload'}
                    </button>
                  </div>
                )}
              </div>

              {/* Zoom View - middle, shows when hovering over PDF */}
              <div className="border rounded-lg overflow-hidden">
                <div className="bg-gray-100 px-3 py-2 border-b flex items-center justify-between">
                  <span className="font-medium text-sm text-gray-700">
                    Vergrößerung <span className="text-gray-500 font-normal">({zoomScale}x)</span>
                  </span>
                  {pdfBlobUrl && (
                    <button
                      onClick={() => setShowZoomModal(true)}
                      className="text-blue-600 hover:text-blue-800 flex items-center gap-1 text-xs"
                      title="Vollbild-Zoom öffnen"
                    >
                      <ZoomIn className="h-3 w-3" />
                      Vollbild
                    </button>
                  )}
                </div>
                <div className="h-72 overflow-hidden bg-gray-50">
                  {isHoveringPdf && pdfBlobUrl ? (
                    /* Zoom View */
                    <div
                      className="w-full h-full overflow-hidden relative"
                      style={{ backgroundColor: '#ffffff' }}
                    >
                      <Document file={pdfBlobUrl}>
                        <div
                          style={{
                            position: 'absolute',
                            left: `calc(50% - ${zoomPosition.x * 170 * zoomScale}px)`,
                            top: `calc(50% - ${zoomPosition.y * 240 * zoomScale}px)`,
                          }}
                        >
                          <Page
                            pageNumber={currentPage}
                            width={170 * zoomScale}
                            renderTextLayer={false}
                            renderAnnotationLayer={false}
                          />
                        </div>
                      </Document>
                    </div>
                  ) : (
                    <div className="h-full flex flex-col items-center justify-center text-gray-400 text-sm">
                      <p>Mit Maus über PDF fahren</p>
                      <p className="text-xs mt-1">Klick wechselt 3x/6x</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Parsed Parameters - right, wider */}
              <div className="border rounded-lg overflow-hidden">
                <div className="bg-gray-100 px-3 py-2 border-b flex items-center justify-between">
                  <span className="font-medium text-sm text-gray-700">Geparste Parameter</span>
                  {currentReceipt.pdf_url && (
                    <button
                      onClick={handleReparse}
                      disabled={reparsing}
                      className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 disabled:text-gray-400 disabled:cursor-not-allowed"
                      title="PDF erneut mit Claude Vision parsen"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${reparsing ? 'animate-spin' : ''}`} />
                      {reparsing ? 'Parst...' : 'Neu parsen'}
                    </button>
                  )}
                </div>
                <div className="h-72 overflow-y-auto p-3 bg-gray-50">
                  {currentReceipt.parsed_params && Object.keys(currentReceipt.parsed_params).length > 0 ? (
                    <div className="space-y-1.5">
                      {Object.entries(currentReceipt.parsed_params).map(([key, value]) => {
                        if (value === null || value === undefined) return null
                        const labels: Record<string, string> = {
                          receipt_type: 'Typ',
                          provider_name: 'Anbieter',
                          invoice_number: 'Rechnungsnr.',
                          invoice_date: 'Rechnungsdatum',
                          invoice_amount: 'Betrag',
                          insured_person: 'Person',
                          description: 'Beschreibung',
                          treatment_period: 'Behandlungszeitraum',
                          due_date: 'Fälligkeit',
                          submission_date: 'Einreichung',
                          payment_recipient: 'Empfänger',
                          payment_iban: 'IBAN',
                          payment_reference: 'Referenz',
                        }
                        const label = labels[key] || key
                        let displayValue: string
                        if (typeof value === 'number') {
                          displayValue = formatCurrency(value)
                        } else if (key === 'payment_iban') {
                          displayValue = formatIban(String(value))
                        } else {
                          displayValue = String(value)
                        }
                        return (
                          <div key={key} className="flex text-sm">
                            <span className="text-gray-500 w-32 flex-shrink-0">{label}:</span>
                            <span className={`text-gray-700 break-all ${key === 'payment_iban' ? 'font-mono tracking-wider' : 'font-mono'}`}>{displayValue}</span>
                          </div>
                        )
                      })}
                      <p className="text-xs text-gray-400 mt-3 pt-3 border-t">
                        Von Claude Vision extrahiert
                      </p>
                    </div>
                  ) : currentReceipt.raw_text ? (
                    <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono">
                      {currentReceipt.raw_text}
                    </pre>
                  ) : (
                    <div className="h-full flex items-center justify-center text-gray-400 text-sm">
                      <p>Keine Daten</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Receipt Details */}
            <div className="border rounded-lg overflow-hidden">
              <div className="bg-gray-100 px-4 py-2 border-b flex items-center justify-between">
                <span className="font-medium text-sm text-gray-700">Beleg-Details</span>
                {isEditing ? (
                  <div className="flex items-center gap-1">
                    <button
                      onClick={saveEditing}
                      className="p-1 text-green-600 hover:bg-green-50 rounded"
                      title="Speichern"
                    >
                      <Save className="h-4 w-4" />
                    </button>
                    <button
                      onClick={cancelEditing}
                      className="p-1 text-red-600 hover:bg-red-50 rounded"
                      title="Abbrechen"
                    >
                      <XCircle className="h-4 w-4" />
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={startEditing}
                    className="p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded"
                    title="Bearbeiten"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                )}
              </div>
              <div className="p-4 grid grid-cols-2 md:grid-cols-4 gap-4">
                {/* Row 1: Basic Info */}
                <div>
                  <span className="text-xs text-gray-500 block">Anbieter</span>
                  {isEditing ? (
                    <input
                      type="text"
                      value={editValues.provider_name || ''}
                      onChange={(e) => setEditValues({ ...editValues, provider_name: e.target.value })}
                      className="w-full border rounded px-2 py-1 text-sm"
                    />
                  ) : (
                    <span className="text-sm font-medium">{currentReceipt.provider_name || '-'}</span>
                  )}
                </div>
                <div>
                  <span className="text-xs text-gray-500 block">Betrag (€)</span>
                  {isEditing ? (
                    <input
                      type="number"
                      step="0.01"
                      value={editValues.invoice_amount || ''}
                      onChange={(e) => setEditValues({ ...editValues, invoice_amount: parseFloat(e.target.value) || 0 })}
                      className="w-full border rounded px-2 py-1 text-sm"
                    />
                  ) : (
                    <span className="text-sm font-medium">{formatCurrency(currentReceipt.invoice_amount)}</span>
                  )}
                </div>
                <div>
                  <span className="text-xs text-gray-500 block">Rechnungsnummer</span>
                  {isEditing ? (
                    <input
                      type="text"
                      value={editValues.invoice_number || ''}
                      onChange={(e) => setEditValues({ ...editValues, invoice_number: e.target.value })}
                      className="w-full border rounded px-2 py-1 text-sm"
                    />
                  ) : (
                    <span className="text-sm font-medium">{currentReceipt.invoice_number || '-'}</span>
                  )}
                </div>
                <div>
                  <span className="text-xs text-gray-500 block">Rechnungsdatum</span>
                  {isEditing ? (
                    <input
                      type="date"
                      value={editValues.invoice_date || ''}
                      onChange={(e) => setEditValues({ ...editValues, invoice_date: e.target.value })}
                      className="w-full border rounded px-2 py-1 text-sm"
                    />
                  ) : (
                    <span className="text-sm font-medium">{currentReceipt.invoice_date ? formatDate(currentReceipt.invoice_date) : '-'}</span>
                  )}
                </div>

                {/* Row 2: Person, Type, Dates */}
                <div>
                  <span className="text-xs text-gray-500 block">Versicherte Person</span>
                  {isEditing ? (
                    <input
                      type="text"
                      value={editValues.insured_person || ''}
                      onChange={(e) => setEditValues({ ...editValues, insured_person: e.target.value })}
                      className="w-full border rounded px-2 py-1 text-sm"
                    />
                  ) : (
                    <span className="text-sm font-medium">{currentReceipt.insured_person || '-'}</span>
                  )}
                </div>
                <div>
                  <span className="text-xs text-gray-500 block">Typ</span>
                  {isEditing ? (
                    <select
                      value={editValues.receipt_type || 'sonstige'}
                      onChange={(e) => setEditValues({ ...editValues, receipt_type: e.target.value })}
                      className="w-full border rounded px-2 py-1 text-sm"
                    >
                      {receiptTypes.map((t) => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                  ) : (
                    <span className="text-sm font-medium capitalize">{currentReceipt.receipt_type || '-'}</span>
                  )}
                </div>
                <div>
                  <span className="text-xs text-gray-500 block">Einreichungsdatum</span>
                  {isEditing ? (
                    <input
                      type="date"
                      value={editValues.submission_date || ''}
                      onChange={(e) => setEditValues({ ...editValues, submission_date: e.target.value })}
                      className="w-full border rounded px-2 py-1 text-sm"
                    />
                  ) : (
                    <span className="text-sm font-medium">{currentReceipt.submission_date ? formatDate(currentReceipt.submission_date) : '-'}</span>
                  )}
                </div>
                <div>
                  <span className="text-xs text-gray-500 block">Zahlungsfrist</span>
                  {isEditing ? (
                    <input
                      type="date"
                      value={editValues.due_date || ''}
                      onChange={(e) => setEditValues({ ...editValues, due_date: e.target.value })}
                      className="w-full border rounded px-2 py-1 text-sm"
                    />
                  ) : (
                    <span className="text-sm font-medium">{currentReceipt.due_date ? formatDate(currentReceipt.due_date) : '-'}</span>
                  )}
                </div>

                {/* Row 3: Description */}
                <div className="col-span-2 md:col-span-4">
                  <span className="text-xs text-gray-500 block">Beschreibung</span>
                  {isEditing ? (
                    <input
                      type="text"
                      value={editValues.description || ''}
                      onChange={(e) => setEditValues({ ...editValues, description: e.target.value })}
                      className="w-full border rounded px-2 py-1 text-sm"
                    />
                  ) : (
                    <span className="text-sm">{currentReceipt.description || '-'}</span>
                  )}
                </div>

                {/* Row 4: Payment Information */}
                <div className="col-span-2 md:col-span-4 border-t pt-4 mt-2">
                  <span className="text-xs text-gray-500 font-medium block mb-2">Zahlungsinformationen</span>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="relative">
                      <span className="text-xs text-gray-500 block">Empfänger</span>
                      {isEditing ? (
                        <>
                          <input
                            type="text"
                            value={editValues.payment_recipient || ''}
                            onChange={(e) => handleRecipientChange(e.target.value)}
                            onFocus={() => {
                              // Show suggestions if we have input and matches
                              if ((editValues.payment_recipient || '').length >= 2) {
                                handleRecipientChange(editValues.payment_recipient || '')
                              }
                            }}
                            onBlur={() => {
                              // Delay hiding to allow click on suggestion
                              setTimeout(() => setShowRecipientSuggestions(false), 200)
                            }}
                            className="w-full border rounded px-2 py-1 text-sm"
                            placeholder="Tippen zum Suchen..."
                            autoComplete="off"
                          />
                          {/* Suggestions Dropdown - opens upward */}
                          {showRecipientSuggestions && recipientSuggestions.length > 0 && (
                            <div className="absolute z-[100] w-full bottom-full mb-1 bg-white border rounded-md shadow-lg max-h-48 overflow-y-auto">
                              {recipientSuggestions.map((info) => (
                                <button
                                  key={info.id}
                                  type="button"
                                  onClick={() => selectRecipientSuggestion(info)}
                                  className="w-full px-3 py-2 text-left hover:bg-blue-50 border-b last:border-b-0"
                                >
                                  <div className="text-sm font-medium text-gray-900">
                                    {info.payment_recipient || info.provider_pattern}
                                  </div>
                                  <div className="text-xs text-gray-500 font-mono">
                                    {formatIban(info.payment_iban)}
                                  </div>
                                </button>
                              ))}
                            </div>
                          )}
                        </>
                      ) : (
                        <span className="text-sm">{currentReceipt.payment_recipient || '-'}</span>
                      )}
                    </div>
                    <div className="col-span-2">
                      <span className="text-xs text-gray-500 block">IBAN</span>
                      {isEditing ? (
                        <input
                          type="text"
                          value={formatIban(editValues.payment_iban)}
                          onChange={(e) => handleIbanChange(e.target.value)}
                          className="w-full border rounded px-2 py-1 text-sm font-mono tracking-wider"
                          placeholder="DE00 0000 0000 0000 0000 00"
                        />
                      ) : (
                        <span className="text-sm font-mono tracking-wider">{formatIban(currentReceipt.payment_iban) || '-'}</span>
                      )}
                    </div>
                    <div>
                      <span className="text-xs text-gray-500 block">Verwendungszweck</span>
                      {isEditing ? (
                        <input
                          type="text"
                          value={editValues.payment_reference || ''}
                          onChange={(e) => setEditValues({ ...editValues, payment_reference: e.target.value })}
                          className="w-full border rounded px-2 py-1 text-sm"
                          placeholder={generateAutoReference() || 'Rechnungsnr. vom Datum'}
                        />
                      ) : currentReceipt.payment_reference ? (
                        <span className="text-sm">{currentReceipt.payment_reference}</span>
                      ) : generateAutoReference() ? (
                        <span className="text-sm italic text-gray-500">{generateAutoReference()}</span>
                      ) : (
                        <span className="text-sm">-</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Reimbursement Info (if applicable) */}
                {currentReceipt.status === 'reimbursed' && (
                  <div className="col-span-2 md:col-span-4 border-t pt-4 mt-2">
                    <span className="text-xs text-gray-500 font-medium block mb-2">Erstattung</span>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div>
                        <span className="text-xs text-gray-500 block">Erstattet</span>
                        <span className="text-sm font-medium text-green-600">{formatCurrency(currentReceipt.reimbursed_amount)}</span>
                      </div>
                      <div>
                        <span className="text-xs text-gray-500 block">Erstattungsdatum</span>
                        <span className="text-sm font-medium">{currentReceipt.reimbursed_date ? formatDate(currentReceipt.reimbursed_date) : '-'}</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end px-6 py-4 border-t bg-gray-50 rounded-b-lg">
            <button
              onClick={handleClose}
              className="px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300"
            >
              Schließen
            </button>
          </div>
        </div>
      </div>

      {/* PDF Zoom Modal */}
      {showZoomModal && pdfSignedUrl && (
        <PdfZoomModal
          url={pdfSignedUrl}
          filename={currentReceipt.pdf_filename}
          onClose={() => setShowZoomModal(false)}
        />
      )}

      {/* Delete PDF Confirmation Dialog */}
      {showDeletePdfConfirm && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-black/50" onClick={() => setShowDeletePdfConfirm(false)} />
          <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full">
            <div className="px-6 py-4 border-b bg-orange-50 rounded-t-lg">
              <h3 className="text-lg font-semibold text-orange-800">PDF entfernen?</h3>
            </div>
            <div className="px-6 py-4">
              <p className="text-sm text-gray-600 mb-4">
                Das PDF und die zugehörigen geparsten Parameter werden entfernt.
                Du kannst danach ein neues PDF hochladen.
              </p>
              <p className="text-xs text-gray-500">
                Datei: <span className="font-mono">{currentReceipt.pdf_filename}</span>
              </p>
            </div>
            <div className="flex justify-end gap-3 px-6 py-4 border-t bg-gray-50 rounded-b-lg">
              <button
                onClick={() => setShowDeletePdfConfirm(false)}
                className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded"
                disabled={deletingPdf}
              >
                Abbrechen
              </button>
              <button
                onClick={handleDeletePdf}
                disabled={deletingPdf}
                className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 flex items-center gap-2"
              >
                {deletingPdf ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Lösche...
                  </>
                ) : (
                  <>
                    <Trash2 className="h-4 w-4" />
                    Entfernen
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Save IBAN Dialog */}
      {showSaveIbanDialog && pendingIbanSave && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-black/50" onClick={() => {
            setShowSaveIbanDialog(false)
            setPendingIbanSave(null)
          }} />
          <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Bankverbindung speichern?</h3>
            <p className="text-sm text-gray-600 mb-4">
              Soll die Bankverbindung f&uuml;r <strong>{pendingIbanSave.recipient}</strong> gespeichert werden?
              Sie wird dann bei zuk&uuml;nftigen Belegen automatisch ausgef&uuml;llt.
            </p>
            <div className="bg-gray-50 rounded p-3 mb-4 text-sm font-mono">
              IBAN: {formatIban(pendingIbanSave.iban)}
            </div>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowSaveIbanDialog(false)
                  setPendingIbanSave(null)
                }}
                className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded"
              >
                Nein
              </button>
              <button
                onClick={saveIbanToProvider}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                Ja, speichern
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
