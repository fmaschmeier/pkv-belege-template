import React, { useState, useRef, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Document, Page } from 'react-pdf'
import { settlementsApi } from '../lib/api'
import type { Settlement, SettlementItem } from '../lib/api'
import { formatDate, formatCurrency } from '../lib/utils'
import { X, Upload, FileText, XCircle, Pencil, Save, ExternalLink, Loader2, ZoomIn, ChevronLeft, ChevronRight } from 'lucide-react'
import PdfZoomModal from './PdfZoomModal'
import '../lib/pdfConfig'

interface SettlementDetailModalProps {
  settlement: Settlement
  highlightItemId?: string | null
  onClose: () => void
}

export default function SettlementDetailModal({
  settlement,
  highlightItemId,
  onClose,
}: SettlementDetailModalProps) {
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [editingItemId, setEditingItemId] = useState<string | null>(null)
  const [editValues, setEditValues] = useState<Partial<SettlementItem>>({})
  const [currentSettlement, setCurrentSettlement] = useState(settlement)
  const [pdfSignedUrl, setPdfSignedUrl] = useState<string | null>(null)
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null)
  const [loadingPdf, setLoadingPdf] = useState(false)
  const [showZoomModal, setShowZoomModal] = useState(false)
  const [numPages, setNumPages] = useState<number>(1)
  const [currentPage, setCurrentPage] = useState<number>(1)
  const [isHoveringPdf, setIsHoveringPdf] = useState(false)
  const [zoomPosition, setZoomPosition] = useState({ x: 0.5, y: 0.5 })
  const [zoomScale, setZoomScale] = useState(3)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pdfContainerRef = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()

  // Load signed URL when modal opens (if pdf exists)
  useEffect(() => {
    if (settlement.pdf_url) {
      loadSignedUrl()
    }
  }, [settlement.id, settlement.pdf_url])

  const loadSignedUrl = async () => {
    setLoadingPdf(true)
    try {
      const result = await settlementsApi.getPdfUrl(settlement.id)
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
      const result = await settlementsApi.uploadPdf(settlement.id, file)
      setMessage({ type: 'success', text: result.message })
      // Update local state with storage path and load signed URL
      setCurrentSettlement(prev => ({ ...prev, pdf_url: result.storage_path }))
      queryClient.invalidateQueries({ queryKey: ['settlements'] })
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

  const startEditing = (item: SettlementItem) => {
    setEditingItemId(item.id)
    setEditValues({
      description: item.description || '',
      invoice_amount: item.invoice_amount,
      reimbursed_amount: item.reimbursed_amount,
      treatment_period: item.treatment_period || '',
      insured_person: item.insured_person || '',
      payment_status: item.payment_status,
      payment_note: item.payment_note || '',
      notes: item.notes || '',
    })
  }

  const cancelEditing = () => {
    setEditingItemId(null)
    setEditValues({})
  }

  const saveEditing = async (itemId: string) => {
    try {
      await settlementsApi.updateItem(itemId, editValues)
      setMessage({ type: 'success', text: 'Position aktualisiert' })
      // Update local state
      setCurrentSettlement(prev => ({
        ...prev,
        settlement_items: prev.settlement_items.map(item =>
          item.id === itemId ? { ...item, ...editValues } : item
        ),
      }))
      queryClient.invalidateQueries({ queryKey: ['settlements'] })
      queryClient.invalidateQueries({ queryKey: ['items'] })
      setEditingItemId(null)
      setEditValues({})
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Speichern fehlgeschlagen',
      })
    }
  }

  const handleClose = () => {
    if (editingItemId) {
      if (window.confirm('Du hast ungespeicherte Änderungen. Wirklich schließen?')) {
        setEditingItemId(null)
        setEditValues({})
        onClose()
      }
    } else {
      onClose()
    }
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
                Leistungsabrechnung {currentSettlement.settlement_number}
              </h2>
              <p className="text-sm text-gray-500">
                {formatDate(currentSettlement.settlement_date)} |
                Rechnung: {formatCurrency(currentSettlement.total_invoiced)} |
                Erstattet: {formatCurrency(currentSettlement.total_reimbursed)}
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
            {/* PDF + Zoom + Raw Text Section - 3 columns */}
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
                    <a
                      href={pdfSignedUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:text-blue-800 text-xs"
                      title="PDF öffnen"
                    >
                      <ExternalLink className="h-3 w-3" />
                    </a>
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
                ) : currentSettlement.pdf_url ? (
                  <div className="h-72 flex flex-col items-center justify-center bg-gray-50 text-red-500">
                    <XCircle className="h-8 w-8 mb-2" />
                    <p className="text-xs">Fehler</p>
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

              {/* Zoom View - middle */}
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

              {/* Raw Text - right, wider */}
              <div className="border rounded-lg overflow-hidden">
                <div className="bg-gray-100 px-3 py-2 border-b">
                  <span className="font-medium text-sm text-gray-700">Geparster Text</span>
                </div>
                <div className="h-72 overflow-y-auto p-3 bg-gray-50">
                  {currentSettlement.raw_text ? (
                    <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono">
                      {currentSettlement.raw_text}
                    </pre>
                  ) : (
                    <div className="h-full flex items-center justify-center text-gray-400 text-sm">
                      <p>Kein Text verfügbar</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Items Table */}
            <div className="border rounded-lg overflow-hidden">
              <div className="bg-gray-100 px-4 py-2 border-b">
                <span className="font-medium text-sm text-gray-700">
                  Positionen ({currentSettlement.settlement_items.length})
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Beleg</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Person</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Beschreibung</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Zeitraum</th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Rechnung</th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Erstattet</th>
                      <th className="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase">Aktion</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {currentSettlement.settlement_items.map((item) => {
                      const isEditing = editingItemId === item.id
                      const isHighlighted = highlightItemId === item.id

                      return (
                        <React.Fragment key={item.id}>
                        <tr
                          className={`${isHighlighted ? 'bg-yellow-50 ring-2 ring-yellow-400 ring-inset' : 'hover:bg-gray-50'}`}
                        >
                          <td className="px-3 py-2 whitespace-nowrap text-sm font-medium text-gray-900">
                            {item.receipt_number}
                          </td>
                          <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-700">
                            {isEditing ? (
                              <input
                                type="text"
                                value={editValues.insured_person || ''}
                                onChange={(e) => setEditValues({ ...editValues, insured_person: e.target.value })}
                                className="w-full border rounded px-2 py-1 text-sm"
                              />
                            ) : (
                              item.insured_person || '-'
                            )}
                          </td>
                          <td className="px-3 py-2 text-sm text-gray-700 max-w-xs">
                            {isEditing ? (
                              <input
                                type="text"
                                value={editValues.description || ''}
                                onChange={(e) => setEditValues({ ...editValues, description: e.target.value })}
                                className="w-full border rounded px-2 py-1 text-sm"
                              />
                            ) : (
                              <span className="truncate block" title={item.description || ''}>
                                {item.description || '-'}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-500">
                            {isEditing ? (
                              <input
                                type="text"
                                value={editValues.treatment_period || ''}
                                onChange={(e) => setEditValues({ ...editValues, treatment_period: e.target.value })}
                                className="w-24 border rounded px-2 py-1 text-sm"
                              />
                            ) : (
                              item.treatment_period || '-'
                            )}
                          </td>
                          <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-900 text-right">
                            {isEditing ? (
                              <input
                                type="number"
                                step="0.01"
                                value={editValues.invoice_amount || ''}
                                onChange={(e) => setEditValues({ ...editValues, invoice_amount: parseFloat(e.target.value) || 0 })}
                                className="w-24 border rounded px-2 py-1 text-sm text-right"
                              />
                            ) : (
                              formatCurrency(item.invoice_amount)
                            )}
                          </td>
                          <td className="px-3 py-2 whitespace-nowrap text-sm text-green-600 text-right font-medium">
                            {isEditing ? (
                              <input
                                type="number"
                                step="0.01"
                                value={editValues.reimbursed_amount || ''}
                                onChange={(e) => setEditValues({ ...editValues, reimbursed_amount: parseFloat(e.target.value) || 0 })}
                                className="w-24 border rounded px-2 py-1 text-sm text-right"
                              />
                            ) : (
                              formatCurrency(item.reimbursed_amount)
                            )}
                          </td>
                          <td className="px-3 py-2 whitespace-nowrap text-center">
                            {isEditing ? (
                              <div className="flex items-center justify-center gap-1">
                                <button
                                  onClick={() => saveEditing(item.id)}
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
                                onClick={() => startEditing(item)}
                                className="p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded"
                                title="Bearbeiten"
                              >
                                <Pencil className="h-4 w-4" />
                              </button>
                            )}
                          </td>
                        </tr>
                        {/* Edit row for notes - only shown when editing */}
                        {isEditing && (
                          <tr className="bg-blue-50">
                            <td className="px-3 py-2 text-xs text-gray-500 font-medium">
                              Anmerkungen:
                            </td>
                            <td colSpan={6} className="px-3 py-2">
                              <input
                                type="text"
                                value={editValues.notes || ''}
                                onChange={(e) => setEditValues({ ...editValues, notes: e.target.value })}
                                className="w-full border rounded px-2 py-1 text-sm"
                                placeholder="Anmerkungen der PKV (z.B. Ablehnung, Hinweise...)"
                              />
                            </td>
                          </tr>
                        )}
                        {/* Show notes row when not editing but notes exist */}
                        {!isEditing && item.notes && (
                          <tr className="bg-orange-50">
                            <td className="px-3 py-1 text-xs text-gray-500">
                              Anmerkung:
                            </td>
                            <td colSpan={6} className="px-3 py-1 text-xs text-orange-700">
                              {item.notes}
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                      )
                    })}
                  </tbody>
                </table>
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
          filename={currentSettlement.pdf_filename}
          onClose={() => setShowZoomModal(false)}
        />
      )}
    </div>
  )
}
