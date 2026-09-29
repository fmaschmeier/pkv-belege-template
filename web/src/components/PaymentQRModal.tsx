import { useState, useEffect, useRef } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { Document, Page } from 'react-pdf'
import { receiptsApi } from '../lib/api'
import type { Receipt, PaymentDefaults } from '../lib/api'
import { formatCurrency } from '../lib/utils'
import { X, Loader2, AlertCircle, CheckCircle, Copy, Check, ChevronLeft, ChevronRight, ZoomIn } from 'lucide-react'
import '../lib/pdfConfig'

interface PaymentQRModalProps {
  receipt: Receipt
  onClose: () => void
  onMarkPaid?: () => void
}

export default function PaymentQRModal({ receipt, onClose, onMarkPaid }: PaymentQRModalProps) {
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [markingPaid, setMarkingPaid] = useState(false)
  const [markedPaid, setMarkedPaid] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [loadingPdf, setLoadingPdf] = useState(false)

  // Form fields
  const [recipient, setRecipient] = useState('')
  const [iban, setIban] = useState('')
  const [reference, setReference] = useState('')
  const [amount, setAmount] = useState(0)

  // QR Code data
  const [qrData, setQrData] = useState<string | null>(null)
  const [ibanValid, setIbanValid] = useState(false)
  const [ibanError, setIbanError] = useState<string | null>(null)

  // PDF preview
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null)
  const [numPages, setNumPages] = useState<number>(1)
  const [currentPage, setCurrentPage] = useState<number>(1)
  const [isHoveringPdf, setIsHoveringPdf] = useState(false)
  const [zoomPosition, setZoomPosition] = useState({ x: 0.5, y: 0.5 })
  const [zoomScale, setZoomScale] = useState(3)
  const pdfContainerRef = useRef<HTMLDivElement>(null)

  // Load defaults on mount
  useEffect(() => {
    loadDefaults()
  }, [receipt.id])

  // Load PDF for preview
  useEffect(() => {
    const loadPdf = async () => {
      if (!receipt.pdf_url) return
      setLoadingPdf(true)
      try {
        const result = await receiptsApi.getPdfUrl(receipt.id)
        // Load as blob to avoid CORS issues
        const response = await fetch(result.signed_url)
        const blob = await response.blob()
        const blobUrl = URL.createObjectURL(blob)
        setPdfBlobUrl(blobUrl)
      } catch (err) {
        console.error('Failed to load PDF:', err)
      } finally {
        setLoadingPdf(false)
      }
    }
    loadPdf()

    return () => {
      if (pdfBlobUrl) {
        URL.revokeObjectURL(pdfBlobUrl)
      }
    }
  }, [receipt.id, receipt.pdf_url])

  const loadDefaults = async () => {
    setLoading(true)
    setError(null)
    try {
      const defaults: PaymentDefaults = await receiptsApi.getPaymentDefaults(receipt.id)
      setRecipient(defaults.recipient)
      setIban(defaults.iban)
      setReference(defaults.reference)
      setAmount(defaults.amount)
      setIbanValid(defaults.iban_valid)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Laden der Zahlungsdaten')
    } finally {
      setLoading(false)
    }
  }

  const generateQR = async () => {
    if (!recipient || !iban || !amount) {
      setError('Bitte alle Felder ausfüllen')
      return
    }

    setGenerating(true)
    setError(null)
    setIbanError(null)

    try {
      const result = await receiptsApi.generatePaymentQR(receipt.id, {
        recipient,
        iban,
        amount,
        reference,
      })

      if (!result.success) {
        setIbanValid(false)
        setIbanError(result.error || 'IBAN ungültig')
        setQrData(null)
      } else {
        setIbanValid(true)
        setQrData(result.qr_data)
        setIban(result.iban) // Update with cleaned IBAN
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler bei QR-Code Generierung')
    } finally {
      setGenerating(false)
    }
  }

  const handleMarkPaid = async () => {
    setMarkingPaid(true)
    setError(null)
    try {
      const today = new Date().toISOString().split('T')[0]
      await receiptsApi.update(receipt.id, {
        paid_date: today,
      } as Partial<Receipt>)
      setMarkedPaid(true)
      onMarkPaid?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Markieren als bezahlt')
    } finally {
      setMarkingPaid(false)
    }
  }

  const copyIban = () => {
    navigator.clipboard.writeText(iban.replace(/\s/g, ''))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Format IBAN with spaces for display
  const formatIban = (value: string) => {
    const clean = value.replace(/\s/g, '').toUpperCase()
    return clean.replace(/(.{4})/g, '$1 ').trim()
  }

  // PDF mouse handling
  const handlePdfMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!pdfContainerRef.current) return
    const rect = pdfContainerRef.current.getBoundingClientRect()
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height))
    setZoomPosition({ x, y })
  }

  const handlePdfClick = () => {
    setZoomScale(prev => prev === 3 ? 6 : 3)
  }

  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages)
    setCurrentPage(1)
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        {/* Backdrop */}
        <div className="fixed inset-0 bg-black/50" onClick={onClose} />

        {/* Modal - wider for 3-column layout */}
        <div className="relative bg-white rounded-lg shadow-xl max-w-6xl w-full">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b bg-gray-50 rounded-t-lg">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">SEPA-Überweisung</h2>
              <p className="text-sm text-gray-500">
                {receipt.provider_name} - {formatCurrency(receipt.invoice_amount)}
              </p>
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X className="h-6 w-6" />
            </button>
          </div>

          {/* Content - 3-column layout */}
          <div className="p-6">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
              </div>
            ) : (
              <>
                {error && (
                  <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-md flex items-center gap-2">
                    <AlertCircle className="h-5 w-5 flex-shrink-0" />
                    {error}
                  </div>
                )}

                <div className="grid grid-cols-[1fr_200px_1.3fr] gap-4">
                  {/* Left column: Form Fields - use flex to align QR button with PDF/Zoom box bottom */}
                  <div className="flex flex-col">
                    {/* Content aligned with PDF/Zoom boxes (360px = header ~40px + h-80 320px) */}
                    <div className="flex flex-col min-h-[360px]">
                      {/* Form fields */}
                      <div className="space-y-3">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            Empfänger
                          </label>
                          <input
                            type="text"
                            value={recipient}
                            onChange={(e) => setRecipient(e.target.value)}
                            maxLength={70}
                            className="w-full border rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            placeholder="Zahlungsempfänger"
                          />
                        </div>

                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            IBAN
                            {ibanValid && (
                              <span className="ml-2 text-green-600 text-xs">
                                <CheckCircle className="h-3 w-3 inline" /> Gültig
                              </span>
                            )}
                            {ibanError && (
                              <span className="ml-2 text-red-600 text-xs">
                                <AlertCircle className="h-3 w-3 inline" /> {ibanError}
                              </span>
                            )}
                          </label>
                          <div className="flex gap-1">
                            <input
                              type="text"
                              value={formatIban(iban)}
                              onChange={(e) => setIban(e.target.value.replace(/\s/g, ''))}
                              maxLength={42}
                              className={`flex-1 border rounded-md px-2 py-2 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                                ibanError ? 'border-red-300 bg-red-50' : ''
                              }`}
                              placeholder="DE89 3704 0044 ..."
                            />
                            <button
                              onClick={copyIban}
                              className="px-2 py-2 border rounded-md hover:bg-gray-50"
                              title="IBAN kopieren"
                            >
                              {copied ? (
                                <Check className="h-4 w-4 text-green-600" />
                              ) : (
                                <Copy className="h-4 w-4 text-gray-400" />
                              )}
                            </button>
                          </div>
                        </div>

                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            Betrag (EUR)
                          </label>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            value={amount.toFixed(2)}
                            onChange={(e) => setAmount(parseFloat(e.target.value) || 0)}
                            className="w-full border rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          />
                        </div>

                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            Verwendungszweck
                          </label>
                          <input
                            type="text"
                            value={reference}
                            onChange={(e) => setReference(e.target.value)}
                            maxLength={140}
                            className="w-full border rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            placeholder="Rechnung Nr. ..."
                          />
                        </div>
                      </div>

                      {/* Spacer to push QR button to bottom */}
                      <div className="flex-1 min-h-4" />

                      {/* QR Button - aligned with PDF/Zoom box bottom edge */}
                      <button
                        onClick={generateQR}
                        disabled={generating || !recipient || !iban || !amount}
                        className="w-full py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                      >
                        {generating ? (
                          <>
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Generiere...
                          </>
                        ) : (
                          'QR-Code generieren'
                        )}
                      </button>
                    </div>

                    {/* QR Code Display - appears below the aligned area */}
                    {qrData && (
                      <div className="pt-6 text-center">
                        <div className="inline-block p-2 bg-white border rounded-lg shadow-sm">
                          <QRCodeSVG
                            value={qrData}
                            size={140}
                            level="M"
                            includeMargin={true}
                          />
                        </div>
                        <p className="mt-2 text-xs text-gray-500">
                          Scanne mit Banking-App
                        </p>
                        {/* Mark as paid button */}
                        {!receipt.paid_date && !markedPaid ? (
                          <button
                            onClick={handleMarkPaid}
                            disabled={markingPaid}
                            className="mt-3 w-full py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 flex items-center justify-center gap-2 text-sm"
                          >
                            {markingPaid ? (
                              <>
                                <Loader2 className="h-4 w-4 animate-spin" />
                                Markiere...
                              </>
                            ) : (
                              <>
                                <CheckCircle className="h-4 w-4" />
                                Jetzt als bezahlt markieren
                              </>
                            )}
                          </button>
                        ) : (markedPaid || receipt.paid_date) && (
                          <div className="mt-3 py-2 bg-green-50 text-green-700 rounded-md flex items-center justify-center gap-2 text-sm">
                            <CheckCircle className="h-4 w-4" />
                            Als bezahlt markiert
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Middle column: PDF Preview */}
                  <div className="border rounded-lg overflow-hidden self-start">
                    <div className="bg-gray-100 px-3 py-2 border-b flex items-center justify-between">
                      <span className="font-medium text-sm text-gray-700">PDF</span>
                      {numPages > 1 && (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                            disabled={currentPage <= 1}
                            className="p-0.5 rounded hover:bg-gray-200 disabled:opacity-30"
                          >
                            <ChevronLeft className="w-3 h-3" />
                          </button>
                          <span className="text-xs text-gray-500">{currentPage}/{numPages}</span>
                          <button
                            onClick={() => setCurrentPage(p => Math.min(numPages, p + 1))}
                            disabled={currentPage >= numPages}
                            className="p-0.5 rounded hover:bg-gray-200 disabled:opacity-30"
                          >
                            <ChevronRight className="w-3 h-3" />
                          </button>
                        </div>
                      )}
                    </div>
                    <div className="h-80 flex items-center justify-center bg-gray-50">
                      {loadingPdf ? (
                        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
                      ) : pdfBlobUrl ? (
                        <div
                          ref={pdfContainerRef}
                          className="relative cursor-crosshair"
                          onMouseMove={handlePdfMouseMove}
                          onMouseEnter={() => setIsHoveringPdf(true)}
                          onMouseLeave={() => setIsHoveringPdf(false)}
                          onClick={handlePdfClick}
                        >
                          <Document
                            file={pdfBlobUrl}
                            onLoadSuccess={onDocumentLoadSuccess}
                            loading={<Loader2 className="h-6 w-6 animate-spin text-gray-400" />}
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
                      ) : (
                        <div className="text-center text-gray-400 text-sm">
                          <p>Kein PDF</p>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Right column: Zoom View */}
                  <div className="border rounded-lg overflow-hidden self-start">
                    <div className="bg-gray-100 px-3 py-2 border-b flex items-center justify-between">
                      <span className="font-medium text-sm text-gray-700">Vergrößerung</span>
                      <span className="text-xs text-gray-500 flex items-center gap-1">
                        <ZoomIn className="w-3 h-3" />
                        {zoomScale}x
                      </span>
                    </div>
                    <div className="h-80 overflow-hidden bg-gray-50">
                      {pdfBlobUrl && isHoveringPdf ? (
                        <div
                          style={{
                            width: '100%',
                            height: '100%',
                            overflow: 'hidden',
                          }}
                        >
                          <div
                            style={{
                              transform: `translate(${-zoomPosition.x * 170 * zoomScale + 140}px, ${-zoomPosition.y * 240 * zoomScale + 160}px)`,
                            }}
                          >
                            <Document file={pdfBlobUrl} loading="">
                              <Page
                                pageNumber={currentPage}
                                width={170 * zoomScale}
                                renderTextLayer={false}
                                renderAnnotationLayer={false}
                              />
                            </Document>
                          </div>
                        </div>
                      ) : (
                        <div className="h-full flex flex-col items-center justify-center text-gray-400 text-sm">
                          <p>Mit Maus über PDF fahren</p>
                          <p className="text-xs mt-1">Klick wechselt 3x/6x</p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* QR Code summary below if generated */}
                {qrData && (
                  <div className="mt-4 p-3 bg-gray-50 rounded-lg text-center text-xs text-gray-500">
                    <strong>Empfänger:</strong> {recipient} | <strong>IBAN:</strong> {formatIban(iban)} | <strong>Betrag:</strong> {formatCurrency(amount)} | <strong>Verwendungszweck:</strong> {reference}
                  </div>
                )}
              </>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end px-6 py-4 border-t bg-gray-50 rounded-b-lg">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300"
            >
              Schließen
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
