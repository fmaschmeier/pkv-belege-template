import { useState, useRef, useEffect, useMemo } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { receiptsApi, bankApi, rulesApi, itemsApi } from '../lib/api'
import type { Receipt, SuggestedTransaction, SuggestedTransactionLinkedInfo, BankTransaction, ItemMatch } from '../lib/api'
import { formatDate, formatCurrency, extractPersonFromDescription } from '../lib/utils'
import { Upload, FileText, Clock, CheckCircle, XCircle, AlertTriangle, RefreshCw, CreditCard, Banknote, X, Link2, Unlink, Info, Eye, Trash2 } from 'lucide-react'
import ReceiptDetailModal from '../components/ReceiptDetailModal'
import PaymentQRModal from '../components/PaymentQRModal'

// Short date format (DD.MM.YY)
function formatDateShort(dateStr: string | null | undefined): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return ''
  const day = date.getDate().toString().padStart(2, '0')
  const month = (date.getMonth() + 1).toString().padStart(2, '0')
  const year = date.getFullYear().toString().slice(-2)
  return `${day}.${month}.${year}`
}

// Erstattungsstatus (PKV)
function getReimbursementBadge(receipt: Receipt, showDetails = false) {
  const today = new Date()
  const submissionDate = receipt.submission_date ? new Date(receipt.submission_date) : null

  if (receipt.status === 'reimbursed') {
    const shortDate = formatDateShort(receipt.reimbursed_date)
    return (
      <div className="flex flex-col items-center gap-0.5">
        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
          <CheckCircle className="h-3 w-3 mr-1" />
          Erstattet{shortDate && ` ${shortDate}`}
        </span>
        {showDetails && (receipt.settlement_number || receipt.receipt_number) && (
          receipt.settlement_item_id ? (
            <Link
              to={`/items#item-${receipt.settlement_item_id}`}
              className="text-xs text-gray-500 hover:text-gray-700 hover:underline"
            >
              {receipt.settlement_number} / {receipt.receipt_number}
            </Link>
          ) : (
            <span className="text-xs text-gray-500">
              {receipt.settlement_number} / {receipt.receipt_number}
            </span>
          )
        )}
      </div>
    )
  }

  if (receipt.status === 'rejected') {
    return (
      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800">
        <XCircle className="h-3 w-3 mr-1" />
        Abgelehnt
      </span>
    )
  }

  // Check if reimbursement is overdue (>30 days since submission)
  if (submissionDate) {
    const daysSinceSubmission = Math.floor((today.getTime() - submissionDate.getTime()) / (1000 * 60 * 60 * 24))
    if (daysSinceSubmission > 30) {
      return (
        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
          <AlertTriangle className="h-3 w-3 mr-1" />
          Erstattung überfällig
        </span>
      )
    }
  }

  return (
    <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
      <Clock className="h-3 w-3 mr-1" />
      Wartet auf Erstattung
    </span>
  )
}

// Zahlungsstatus (Rechnung bezahlt?)
function getPaymentBadge(receipt: Receipt) {
  const today = new Date()
  today.setHours(0, 0, 0, 0) // Nur Datum vergleichen, keine Uhrzeit
  const dueDate = receipt.due_date ? new Date(receipt.due_date) : null

  // Rezepte werden direkt in der Apotheke bezahlt - keine separate Zahlungsverfolgung
  if (receipt.receipt_type === 'rezept') {
    return (
      <span
        className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800"
        title="Rezepte werden direkt in der Apotheke bezahlt. Keine separate Zahlungsverfolgung."
      >
        <CheckCircle className="h-3 w-3 mr-1" />
        Direktzahlung
      </span>
    )
  }

  if (receipt.paid_date) {
    const shortDate = formatDateShort(receipt.paid_date)
    const paidAmount = receipt.paid_amount
    const invoiceAmount = receipt.invoice_amount || 0
    const hasTransaction = !!receipt.payment_transaction_id

    // Check if partial payment (paid less than invoiced)
    const isPartialPayment = paidAmount && paidAmount < invoiceAmount - 0.01  // 0.01 tolerance for rounding
    // Manual payment without bank transaction
    const isManualPayment = !hasTransaction

    // Yellow for partial or manual payments, green for full payments with proof
    const needsAttention = isPartialPayment || isManualPayment
    const bgColor = needsAttention ? 'bg-yellow-100' : 'bg-green-100'
    const textColor = needsAttention ? 'text-yellow-800' : 'text-green-800'
    const subTextColor = needsAttention ? 'text-yellow-600' : 'text-green-600'
    const Icon = needsAttention ? AlertTriangle : CheckCircle

    return (
      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${bgColor} ${textColor}`}>
        <Icon className="h-3 w-3 mr-1" />
        {isPartialPayment ? (
          <span className="flex flex-col items-start leading-tight">
            <span>{formatCurrency(paidAmount!)}</span>
            <span className={`${subTextColor} text-[10px]`}>{shortDate}</span>
          </span>
        ) : isManualPayment ? (
          <span className="flex flex-col items-start leading-tight">
            <span>Bezahlt {shortDate}</span>
            <span className={`${subTextColor} text-[10px]`}>ohne Beleg</span>
          </span>
        ) : (
          <>Bezahlt{shortDate && ` ${shortDate}`}</>
        )}
      </span>
    )
  }

  // Payment overdue
  if (dueDate && dueDate < today) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
        <AlertTriangle className="h-3 w-3 mr-1" />
        Zahlung überfällig
      </span>
    )
  }

  // Due soon
  if (dueDate) {
    const daysUntilDue = Math.ceil((dueDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
    if (daysUntilDue <= 7) {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800">
          <Clock className="h-3 w-3 mr-1" />
          Bald fällig
        </span>
      )
    }
  }

  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600">
      Offen
    </span>
  )
}

function getReceiptTypeBadge(type: string | null) {
  const types: Record<string, { label: string; color: string }> = {
    pflege: { label: 'Pflege', color: 'bg-purple-100 text-purple-800' },
    rezept: { label: 'Rezept', color: 'bg-green-100 text-green-800' },
    arzt: { label: 'Arzt', color: 'bg-blue-100 text-blue-800' },
    hilfsmittel: { label: 'Hilfsmittel', color: 'bg-orange-100 text-orange-800' },
    sonstige: { label: 'Sonstige', color: 'bg-gray-100 text-gray-800' },
  }

  const config = types[type || 'sonstige'] || types.sonstige

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${config.color}`}>
      {config.label}
    </span>
  )
}

// Payment Link Modal Component
function PaymentLinkModal({
  receipt,
  onClose,
  onSave,
}: {
  receipt: Receipt
  onClose: () => void
  onSave: (receiptId: string, transactionId: string | null, paidDate: string | null, forceUnlink?: boolean) => Promise<{ success: boolean; conflict?: SuggestedTransactionLinkedInfo }>
}) {
  const [selectedTransaction, setSelectedTransaction] = useState<string | null>(receipt.payment_transaction_id)
  const [paidDate, setPaidDate] = useState<string>(receipt.paid_date || '')
  const [saving, setSaving] = useState(false)
  const [conflictInfo, setConflictInfo] = useState<SuggestedTransactionLinkedInfo | null>(null)

  // Calculate date range for manual selection (±30 days around due_date or invoice_date)
  const DAYS_RANGE = 30  // TODO: Make configurable
  const referenceDate = receipt.due_date || receipt.invoice_date || receipt.submission_date
  const referenceDateObj = referenceDate ? new Date(referenceDate) : new Date()
  const dateFrom = new Date(referenceDateObj)
  dateFrom.setDate(dateFrom.getDate() - DAYS_RANGE)
  const dateTo = new Date(referenceDateObj)
  dateTo.setDate(dateTo.getDate() + DAYS_RANGE)
  const dateFromStr = dateFrom.toISOString().split('T')[0]
  const dateToStr = dateTo.toISOString().split('T')[0]

  // Fetch payment suggestions from backend (uses dynamic matching rules)
  const { data: suggestions, isLoading: loadingSuggestions } = useQuery({
    queryKey: ['paymentSuggestions', receipt.id],
    queryFn: () => receiptsApi.suggestPayments(receipt.id),
  })

  // Fetch bank transactions for the relevant time period (based on receipt date)
  // We need to load transactions from the months around the receipt date
  const refYear = referenceDateObj.getFullYear()
  const refMonth = referenceDateObj.getMonth() + 1  // 1-indexed

  // Load 3 months: month before, month of, month after
  const { data: bankDataPrev, isLoading: loadingBankPrev } = useQuery({
    queryKey: ['bankTransactionsForLink', refYear, refMonth - 1],
    queryFn: () => {
      const m = refMonth - 1
      const y = m < 1 ? refYear - 1 : refYear
      const month = m < 1 ? 12 : m
      return bankApi.transactions({ limit: 500, universa_only: false, year: y, month })
    },
  })

  const { data: bankDataCurr, isLoading: loadingBankCurr } = useQuery({
    queryKey: ['bankTransactionsForLink', refYear, refMonth],
    queryFn: () => bankApi.transactions({ limit: 500, universa_only: false, year: refYear, month: refMonth }),
  })

  const { data: bankDataNext, isLoading: loadingBankNext } = useQuery({
    queryKey: ['bankTransactionsForLink', refYear, refMonth + 1],
    queryFn: () => {
      const m = refMonth + 1
      const y = m > 12 ? refYear + 1 : refYear
      const month = m > 12 ? 1 : m
      return bankApi.transactions({ limit: 500, universa_only: false, year: y, month })
    },
  })

  // Combine all transactions from the 3 months
  const allBankTransactions = [
    ...(bankDataPrev?.transactions || []),
    ...(bankDataCurr?.transactions || []),
    ...(bankDataNext?.transactions || []),
  ]

  const matchingTransactions = suggestions?.matching || []
  const sameAmountTransactions = suggestions?.same_amount || []

  // All other payments (for manual selection) - exclude matching and same_amount
  const matchingIds = new Set(matchingTransactions.map((t: SuggestedTransaction) => t.id))
  const sameAmountIds = new Set(sameAmountTransactions.map((t: SuggestedTransaction) => t.id))
  const seenIds = new Set<string>()
  const allNonMatchingPayments = allBankTransactions.filter((tx) => {
    if (tx.amount >= 0) return false
    if (matchingIds.has(tx.id) || sameAmountIds.has(tx.id)) return false
    // Deduplicate (same tx might appear in multiple months at boundaries)
    if (seenIds.has(tx.id)) return false
    seenIds.add(tx.id)
    return true
  })

  // Filter by date range (±30 days around reference date)
  const paymentsInRange = allNonMatchingPayments.filter((tx) => {
    const txDate = tx.booking_date
    return txDate >= dateFromStr && txDate <= dateToStr
  })

  // Show payments in range, or all loaded payments as fallback
  const allPayments = paymentsInRange.length > 0 ? paymentsInRange : allNonMatchingPayments
  const showingFallback = paymentsInRange.length === 0 && allNonMatchingPayments.length > 0

  const isLoading = loadingSuggestions || loadingBankPrev || loadingBankCurr || loadingBankNext

  const handleSave = async (forceUnlink = false) => {
    setSaving(true)
    const result = await onSave(receipt.id, selectedTransaction, paidDate || null, forceUnlink)
    setSaving(false)

    if (!result.success && result.conflict) {
      // Show conflict dialog
      setConflictInfo(result.conflict)
    }
  }

  const handleUnlink = async () => {
    setSaving(true)
    await onSave(receipt.id, null, null)
    setSaving(false)
  }

  const handleForceUnlink = async () => {
    setConflictInfo(null)
    await handleSave(true)
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        {/* Backdrop */}
        <div className="fixed inset-0 bg-black/50" onClick={onClose} />

        {/* Modal */}
        <div className="relative bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[90vh] overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b bg-gray-50 rounded-t-lg">
            <h2 className="text-lg font-semibold text-gray-900">Zahlung verknüpfen</h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className="px-6 py-4 space-y-4 overflow-y-auto max-h-[60vh]">
            {/* Receipt Info */}
            <div className="bg-gray-50 rounded-lg p-4 space-y-2">
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Anbieter:</span>
                  <span className="ml-2 font-medium">{receipt.provider_name || '-'}</span>
                </div>
                <div>
                  <span className="text-gray-500">Betrag:</span>
                  <span className="ml-2 font-medium text-blue-600">{formatCurrency(receipt.invoice_amount)}</span>
                </div>
                <div>
                  <span className="text-gray-500">Person:</span>
                  <span className="ml-2 font-medium">{receipt.insured_person || '-'}</span>
                </div>
                <div>
                  <span className="text-gray-500">Rechnungsnr.:</span>
                  <span className="ml-2 font-medium font-mono">{receipt.invoice_number || '-'}</span>
                </div>
                <div>
                  <span className="text-gray-500">Rechnungsdatum:</span>
                  <span className="ml-2 font-medium">{receipt.invoice_date ? formatDate(receipt.invoice_date) : '-'}</span>
                </div>
                <div>
                  <span className="text-gray-500">Fälligkeit:</span>
                  <span className="ml-2 font-medium">{receipt.due_date ? formatDate(receipt.due_date) : '-'}</span>
                </div>
              </div>
            </div>

            {/* Payment Link Section */}
            <div className="space-y-3">
              <h3 className="font-medium text-gray-900 flex items-center gap-2">
                <CreditCard className="h-4 w-4" />
                Zahlung verknüpfen
              </h3>

              {isLoading ? (
                <div className="text-center py-4">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600 mx-auto"></div>
                </div>
              ) : (
                <>
                  {/* Matching transactions (exact amount) */}
                  {matchingTransactions.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-sm text-green-600 font-medium">Passende Transaktionen ({matchingTransactions.length}):</p>
                      <div className="space-y-1 max-h-40 overflow-y-auto">
                        {matchingTransactions.map((tx: SuggestedTransaction) => {
                          const personName = extractPersonFromDescription(tx.description)
                          const isLinked = !!tx.linked_to_receipt
                          return (
                            <label
                              key={tx.id}
                              className={`flex items-center gap-3 p-2 rounded border cursor-pointer transition ${
                                selectedTransaction === tx.id
                                  ? 'border-blue-500 bg-blue-50'
                                  : isLinked
                                    ? 'border-orange-200 bg-orange-50 hover:border-orange-300'
                                    : 'border-green-200 bg-green-50 hover:border-green-300'
                              }`}
                            >
                              <input
                                type="radio"
                                name="transaction"
                                checked={selectedTransaction === tx.id}
                                onChange={() => {
                                  setSelectedTransaction(tx.id)
                                  setPaidDate(tx.booking_date)
                                }}
                                className="text-blue-600"
                              />
                              <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium flex items-center gap-2">
                                  {formatDate(tx.booking_date)}
                                  {tx.treatment_date && <span className="text-gray-500">(Leistungstag: {tx.treatment_date})</span>}
                                  {isLinked && (
                                    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-800">
                                      <Link2 className="h-3 w-3 mr-1" />
                                      vergeben
                                    </span>
                                  )}
                                </div>
                                <div className="text-xs text-gray-600 truncate">
                                  {tx.description.substring(0, 50)}...
                                  {personName && <span className="ml-1 text-blue-600">({personName})</span>}
                                </div>
                                {isLinked && tx.linked_to_receipt && (
                                  <div className="text-xs text-orange-600 mt-0.5">
                                    Bereits zugeordnet: {tx.linked_to_receipt.provider_name || 'Unbekannt'} | {formatCurrency(tx.linked_to_receipt.invoice_amount)} | {tx.linked_to_receipt.invoice_date ? formatDate(tx.linked_to_receipt.invoice_date) : '-'}
                                  </div>
                                )}
                              </div>
                              <span className="text-sm font-medium text-red-600 whitespace-nowrap">
                                {formatCurrency(tx.amount)}
                              </span>
                            </label>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {/* Same amount but different provider */}
                  {sameAmountTransactions.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-sm text-yellow-600 font-medium">
                        Gleicher Betrag, anderer Anbieter ({sameAmountTransactions.length}):
                      </p>
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {sameAmountTransactions.map((tx: SuggestedTransaction) => {
                          const isLinked = !!tx.linked_to_receipt
                          return (
                            <label
                              key={tx.id}
                              className={`flex items-center gap-3 p-2 rounded border cursor-pointer transition ${
                                selectedTransaction === tx.id
                                  ? 'border-blue-500 bg-blue-50'
                                  : isLinked
                                    ? 'border-orange-200 bg-orange-50 hover:border-orange-300'
                                    : 'border-yellow-200 bg-yellow-50 hover:border-yellow-300'
                              }`}
                            >
                              <input
                                type="radio"
                                name="transaction"
                                checked={selectedTransaction === tx.id}
                                onChange={() => {
                                  setSelectedTransaction(tx.id)
                                  setPaidDate(tx.booking_date)
                                }}
                                className="text-blue-600"
                              />
                              <div className="flex-1 min-w-0">
                                <div className="text-sm flex items-center gap-2">
                                  {formatDate(tx.booking_date)}
                                  {tx.treatment_date && <span className="text-gray-500">(LT: {tx.treatment_date})</span>}
                                  {isLinked && (
                                    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-800">
                                      <Link2 className="h-3 w-3 mr-1" />
                                      vergeben
                                    </span>
                                  )}
                                </div>
                                <div className="text-xs text-gray-600 truncate">{tx.description.substring(0, 50)}...</div>
                                {isLinked && tx.linked_to_receipt && (
                                  <div className="text-xs text-orange-600 mt-0.5">
                                    Bereits zugeordnet: {tx.linked_to_receipt.provider_name || 'Unbekannt'} | {formatCurrency(tx.linked_to_receipt.invoice_amount)} | {tx.linked_to_receipt.invoice_date ? formatDate(tx.linked_to_receipt.invoice_date) : '-'}
                                  </div>
                                )}
                              </div>
                              <span className="text-sm font-medium text-red-600 whitespace-nowrap">
                                {formatCurrency(tx.amount)}
                              </span>
                            </label>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {/* All other payments (manual selection) */}
                  <div className="space-y-2">
                    <p className="text-sm text-gray-500">
                      {showingFallback ? (
                        <>Alle Zahlungen ({allPayments.length}) - keine im Zeitraum {formatDate(dateFromStr)} - {formatDate(dateToStr)}:</>
                      ) : (
                        <>Zahlungen {formatDate(dateFromStr)} - {formatDate(dateToStr)} ({allPayments.length}):</>
                      )}
                    </p>
                    <select
                      value={selectedTransaction || ''}
                      onChange={(e) => {
                        const txId = e.target.value || null
                        setSelectedTransaction(txId)
                        if (txId) {
                          const tx = allPayments.find((t) => t.id === txId) ||
                                     sameAmountTransactions.find((t: SuggestedTransaction) => t.id === txId) ||
                                     matchingTransactions.find((t: SuggestedTransaction) => t.id === txId)
                          if (tx) setPaidDate(tx.booking_date)
                        }
                      }}
                      className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                    >
                      <option value="">-- Keine Verknüpfung --</option>
                      {allPayments.map((tx) => (
                        <option key={tx.id} value={tx.id}>
                          {formatDate(tx.booking_date)} | {formatCurrency(tx.amount)} | {tx.description.substring(0, 40)}...
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Manual paid date */}
                  <div className="space-y-2">
                    <label className="text-sm text-gray-600">Zahlungsdatum (manuell):</label>
                    <input
                      type="date"
                      value={paidDate}
                      onChange={(e) => setPaidDate(e.target.value)}
                      className="border border-gray-300 rounded-md px-3 py-2 text-sm"
                    />
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between px-6 py-4 border-t bg-gray-50 rounded-b-lg">
            <div>
              {receipt.payment_transaction_id && (
                <button
                  onClick={handleUnlink}
                  disabled={saving}
                  className="flex items-center gap-2 px-3 py-2 text-red-600 hover:bg-red-50 rounded-md disabled:opacity-50"
                >
                  <Unlink className="h-4 w-4" />
                  Verknüpfung entfernen
                </button>
              )}
            </div>
            <div className="flex gap-2">
              <button
                onClick={onClose}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md"
              >
                Abbrechen
              </button>
              <button
                onClick={() => handleSave()}
                disabled={saving}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                ) : (
                  <Link2 className="h-4 w-4" />
                )}
                Speichern
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Conflict Dialog */}
      {conflictInfo && (
        <div className="fixed inset-0 z-[60] overflow-y-auto">
          <div className="flex min-h-screen items-center justify-center p-4">
            <div className="fixed inset-0 bg-black/50" onClick={() => setConflictInfo(null)} />
            <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full">
              <div className="px-6 py-4 border-b bg-orange-50 rounded-t-lg">
                <h2 className="text-lg font-semibold text-orange-800 flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5" />
                  Zahlung bereits zugeordnet
                </h2>
              </div>

              <div className="px-6 py-4 space-y-4">
                <p className="text-sm text-gray-600">
                  Diese Zahlung ist bereits einem anderen Beleg zugeordnet:
                </p>

                <div className="bg-gray-50 rounded-lg p-3 space-y-1 text-sm">
                  <div><span className="text-gray-500">Anbieter:</span> <span className="font-medium">{conflictInfo.provider_name || '-'}</span></div>
                  <div><span className="text-gray-500">Betrag:</span> <span className="font-medium">{formatCurrency(conflictInfo.invoice_amount)}</span></div>
                  <div><span className="text-gray-500">Rechnungsdatum:</span> <span className="font-medium">{conflictInfo.invoice_date ? formatDate(conflictInfo.invoice_date) : '-'}</span></div>
                </div>

                <p className="text-sm text-gray-600">
                  Möchtest du die Zahlung vom anderen Beleg entfernen und diesem Beleg zuordnen?
                </p>
              </div>

              <div className="flex items-center justify-end gap-2 px-6 py-4 border-t bg-gray-50 rounded-b-lg">
                <button
                  onClick={() => setConflictInfo(null)}
                  className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md"
                >
                  Abbrechen
                </button>
                <button
                  onClick={handleForceUnlink}
                  disabled={saving}
                  className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 disabled:opacity-50"
                >
                  <Unlink className="h-4 w-4" />
                  Neu zuordnen
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Create Correction Rule Dialog
function CreateCorrectionRuleDialog({
  fieldName,
  oldValue,
  newValue,
  onClose,
  onSave,
}: {
  fieldName: string
  oldValue: string
  newValue: string
  onClose: () => void
  onSave: () => void
}) {
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try {
      await rulesApi.createCorrection({
        field_name: fieldName,
        raw_value: oldValue,
        corrected_value: newValue,
        active: true,
        description: null,
      })
      onSave()
    } catch (err) {
      // Ignore error - rule might already exist
      onClose()
    }
    setSaving(false)
  }

  const fieldLabels: Record<string, string> = {
    provider_name: 'Anbieter',
    insured_person: 'Versicherte Person',
    description: 'Beschreibung',
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        <div className="fixed inset-0 bg-black/50" onClick={onClose} />
        <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full">
          <div className="px-6 py-4 border-b bg-gray-50 rounded-t-lg">
            <h2 className="text-lg font-semibold text-gray-900">Korrektur speichern?</h2>
          </div>

          <div className="px-6 py-4 space-y-4">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 flex gap-3">
              <Info className="h-5 w-5 text-blue-500 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-blue-800">
                Du hast den <strong>{fieldLabels[fieldName] || fieldName}</strong> korrigiert.
                Soll diese Korrektur für zukünftige Uploads gespeichert werden?
              </div>
            </div>

            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <span className="text-gray-500 w-16">Alt:</span>
                <span className="font-mono bg-red-50 text-red-800 px-2 py-1 rounded truncate flex-1" title={oldValue}>
                  {oldValue}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-gray-500 w-16">Neu:</span>
                <span className="font-mono bg-green-50 text-green-800 px-2 py-1 rounded truncate flex-1" title={newValue}>
                  {newValue}
                </span>
              </div>
            </div>

            <p className="text-xs text-gray-500">
              Bestehende Belege werden nicht geändert.
            </p>
          </div>

          <div className="flex items-center justify-end gap-2 px-6 py-4 border-t bg-gray-50 rounded-b-lg">
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md"
            >
              Nein, nur diesmal
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
              ) : (
                <CheckCircle className="h-4 w-4" />
              )}
              Regel speichern
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// Settlement Link Modal Component - Manuelle Verknüpfung mit Erstattung
function SettlementLinkModal({
  receipt,
  onClose,
  onSave,
}: {
  receipt: Receipt
  onClose: () => void
  onSave: (receiptId: string, settlementItemId: string, reimbursedAmount: number | null, reimbursedDate: string | null) => Promise<void>
}) {
  const [selectedItem, setSelectedItem] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // Search for matching items based on receipt amount, person, and submission date
  const { data: searchResults, isLoading: searchLoading } = useQuery({
    queryKey: ['itemSearch', receipt.invoice_amount, receipt.insured_person, receipt.submission_date],
    queryFn: () => itemsApi.search({
      amount: receipt.invoice_amount || 0,
      person: receipt.insured_person || undefined,
      submission_date: receipt.submission_date || undefined,
    }),
    enabled: !!receipt.invoice_amount,
  })

  // Also load unlinked items for manual selection
  const { data: unlinkedItems, isLoading: unlinkedLoading } = useQuery({
    queryKey: ['unlinkedItems'],
    queryFn: () => itemsApi.unlinked({ limit: 200 }),
  })

  const isLoading = searchLoading || unlinkedLoading

  // Matching items (same amount)
  const matchingItems = searchResults?.matches || []

  // All unlinked items excluding the matching ones
  const matchingIds = new Set(matchingItems.map((m) => m.id))
  const otherItems = (unlinkedItems?.items || []).filter((item) => !matchingIds.has(item.id))

  const handleSave = async () => {
    if (!selectedItem) return

    setSaving(true)

    // Find the selected item to get reimbursed_amount and settlement_date
    const item = matchingItems.find((m) => m.id === selectedItem) ||
                 otherItems.find((i) => i.id === selectedItem)

    await onSave(
      receipt.id,
      selectedItem,
      item?.reimbursed_amount || null,
      item?.settlement_date || null
    )
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        {/* Backdrop */}
        <div className="fixed inset-0 bg-black/50" onClick={onClose} />

        {/* Modal */}
        <div className="relative bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b bg-green-50 rounded-t-lg">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Mit Erstattung verknüpfen</h2>
              <p className="text-sm text-gray-500">
                {receipt.provider_name} - {formatCurrency(receipt.invoice_amount)}
              </p>
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className="px-6 py-4 space-y-4 overflow-y-auto max-h-[60vh]">
            {/* Receipt Info */}
            <div className="bg-gray-50 rounded-lg p-4 space-y-2">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Eingereicht:</span>
                  <span className="ml-2 font-medium">{formatDate(receipt.submission_date)}</span>
                </div>
                <div>
                  <span className="text-gray-500">Betrag:</span>
                  <span className="ml-2 font-medium text-blue-600">{formatCurrency(receipt.invoice_amount)}</span>
                </div>
                <div>
                  <span className="text-gray-500">Person:</span>
                  <span className="ml-2 font-medium">{receipt.insured_person || '-'}</span>
                </div>
                <div>
                  <span className="text-gray-500">Rechnungsdatum:</span>
                  <span className="ml-2 font-medium">{formatDate(receipt.invoice_date)}</span>
                </div>
              </div>
            </div>

            {isLoading ? (
              <div className="text-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
              </div>
            ) : (
              <>
                {/* Matching items (same amount) */}
                {matchingItems.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-sm text-green-600 font-medium">
                      Passende Erstattungen ({matchingItems.length}):
                    </p>
                    <div className="space-y-1 max-h-48 overflow-y-auto">
                      {matchingItems.map((item: ItemMatch) => (
                        <label
                          key={item.id}
                          className={`flex items-center gap-3 p-3 rounded border cursor-pointer transition ${
                            selectedItem === item.id
                              ? 'border-blue-500 bg-blue-50'
                              : 'border-green-200 bg-green-50 hover:border-green-300'
                          }`}
                        >
                          <input
                            type="radio"
                            name="settlementItem"
                            checked={selectedItem === item.id}
                            onChange={() => setSelectedItem(item.id)}
                            className="text-blue-600"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 text-sm font-medium">
                              <span className="text-gray-900">{item.receipt_number}</span>
                              <span className="text-gray-500">|</span>
                              <span className="text-gray-600">{item.settlement_number}</span>
                              <span className="text-gray-500">|</span>
                              <span className="text-gray-600">{formatDate(item.settlement_date)}</span>
                            </div>
                            <div className="text-xs text-gray-600 truncate">
                              {item.insured_person} - {item.description?.substring(0, 40)}
                            </div>
                            {item.treatment_period && (
                              <div className="text-xs text-gray-500">
                                Behandlung: {item.treatment_period}
                              </div>
                            )}
                          </div>
                          <div className="text-right">
                            <div className="text-sm font-medium text-green-600">
                              {formatCurrency(item.reimbursed_amount)}
                            </div>
                            <div className="text-xs text-gray-500">
                              erstattet
                            </div>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>
                )}

                {/* No matches found */}
                {matchingItems.length === 0 && receipt.invoice_amount && (
                  <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm text-yellow-800">
                    Keine Erstattung mit exakt {formatCurrency(receipt.invoice_amount)} gefunden.
                    Du kannst unten manuell eine Erstattung auswählen.
                  </div>
                )}

                {/* Other unlinked items (manual selection) */}
                {otherItems.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-sm text-gray-500">
                      Alle unverknüpften Erstattungen ({otherItems.length}):
                    </p>
                    <select
                      value={selectedItem || ''}
                      onChange={(e) => setSelectedItem(e.target.value || null)}
                      className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                    >
                      <option value="">-- Manuell auswählen --</option>
                      {otherItems.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.receipt_number} | {item.settlement_number} | {formatDate(item.settlement_date)} | {item.insured_person} | {formatCurrency(item.invoice_amount)} → {formatCurrency(item.reimbursed_amount)}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-2 px-6 py-4 border-t bg-gray-50 rounded-b-lg">
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md"
            >
              Abbrechen
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !selectedItem}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50"
            >
              {saving ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
              ) : (
                <Link2 className="h-4 w-4" />
              )}
              Verknüpfen
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// Payment Detail Modal Component
function PaymentDetailModal({
  receipt,
  onClose,
}: {
  receipt: Receipt
  onClose: () => void
}) {
  const [transaction, setTransaction] = useState<BankTransaction | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (receipt.payment_transaction_id) {
      setLoading(true)
      bankApi.getTransaction(receipt.payment_transaction_id)
        .then((tx) => {
          setTransaction(tx)
          setLoading(false)
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : 'Fehler beim Laden')
          setLoading(false)
        })
    }
  }, [receipt.payment_transaction_id])

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        <div className="fixed inset-0 bg-black/50" onClick={onClose} />
        <div className="relative bg-white rounded-lg shadow-xl max-w-lg w-full">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b bg-green-50 rounded-t-lg">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Zahlungsdetails</h2>
              <p className="text-sm text-gray-500">
                {receipt.provider_name} - {formatCurrency(receipt.invoice_amount)}
              </p>
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X className="h-6 w-6" />
            </button>
          </div>

          {/* Content */}
          <div className="p-6">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              </div>
            ) : error ? (
              <div className="p-4 bg-red-50 text-red-700 rounded-md">
                {error}
              </div>
            ) : transaction ? (
              <div className="space-y-4">
                <div className="bg-gray-50 rounded-lg p-4 space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Buchungsdatum:</span>
                    <span className="font-medium">{formatDate(transaction.booking_date)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Wertstellung:</span>
                    <span className="font-medium">{formatDate(transaction.value_date)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Betrag:</span>
                    <span className="font-medium text-red-600">{formatCurrency(transaction.amount)}</span>
                  </div>
                  {transaction.transaction_type && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Umsatzart:</span>
                      <span className="font-medium">{transaction.transaction_type}</span>
                    </div>
                  )}
                </div>

                <div>
                  <span className="text-sm text-gray-500 block mb-1">Buchungstext:</span>
                  <div className="bg-gray-50 rounded-lg p-3 text-sm font-mono whitespace-pre-wrap break-words">
                    {transaction.description}
                  </div>
                </div>
              </div>
            ) : (
              <div className="p-4 bg-yellow-50 text-yellow-700 rounded-md">
                Keine Transaktionsdaten gefunden
              </div>
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

export default function Receipts() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [paymentFilter, setPaymentFilter] = useState<string>('')
  const [reimbursementOverdue, setReimbursementOverdue] = useState(false)
  const [person, setPerson] = useState('')
  const [uploading, setUploading] = useState(false)
  const [matching, setMatching] = useState(false)
  const [matchingPayments, setMatchingPayments] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [paymentLinkReceipt, setPaymentLinkReceipt] = useState<Receipt | null>(null)
  const [detailReceipt, setDetailReceipt] = useState<Receipt | null>(null)
  const [correctionRuleDialog, setCorrectionRuleDialog] = useState<{
    fieldName: string
    oldValue: string
    newValue: string
  } | null>(null)
  const [unlinkReimbursementReceipt, setUnlinkReimbursementReceipt] = useState<Receipt | null>(null)
  const [settlementLinkReceipt, setSettlementLinkReceipt] = useState<Receipt | null>(null)
  const [deleteReceipt, setDeleteReceipt] = useState<Receipt | null>(null)
  const [paymentQRReceipt, setPaymentQRReceipt] = useState<Receipt | null>(null)
  const [paymentDetailReceipt, setPaymentDetailReceipt] = useState<Receipt | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  // Always fetch ALL receipts - filtering happens client-side
  // This ensures rawData.total is always the true total count
  const { data: rawData, isLoading, error } = useQuery({
    queryKey: ['receipts'],
    queryFn: () => receiptsApi.list({ limit: 500 }),
  })

  // Handle URL parameter for deep linking from bank transactions
  useEffect(() => {
    const receiptId = searchParams.get('receipt')
    if (receiptId && rawData?.receipts) {
      const receipt = rawData.receipts.find(r => r.id === receiptId)
      if (receipt) {
        setDetailReceipt(receipt)
        // Clear the URL parameter
        setSearchParams({})
      }
    }
  }, [searchParams, rawData?.receipts, setSearchParams])

  // Calculate sums for each stat category
  const statSums = useMemo(() => {
    if (!rawData?.receipts) return null

    const today = new Date()
    today.setHours(0, 0, 0, 0)

    const allReceipts = rawData.receipts
    const pending = allReceipts.filter(r => r.status === 'submitted')

    // Erstattung überfällig: >30 Tage seit Einreichung
    const reimbursementOverdueReceipts = pending.filter(r => {
      if (!r.submission_date) return false
      const submissionDate = new Date(r.submission_date)
      const daysSince = Math.floor((today.getTime() - submissionDate.getTime()) / (1000 * 60 * 60 * 24))
      return daysSince > 30
    })

    // Unbezahlt (excl. Rezepte)
    const unpaidReceipts = allReceipts.filter(r =>
      !r.paid_date && r.receipt_type !== 'rezept'
    )

    // Zahlung überfällig
    const paymentOverdueReceipts = allReceipts.filter(r =>
      r.due_date &&
      new Date(r.due_date) < today &&
      !r.paid_date &&
      r.receipt_type !== 'rezept'
    )

    return {
      total: allReceipts.reduce((sum, r) => sum + (r.invoice_amount || 0), 0),
      pending: pending.reduce((sum, r) => sum + (r.invoice_amount || 0), 0),
      reimbursementOverdue: reimbursementOverdueReceipts.reduce((sum, r) => sum + (r.invoice_amount || 0), 0),
      unpaid: unpaidReceipts.reduce((sum, r) => sum + (r.invoice_amount || 0), 0),
      paymentOverdue: paymentOverdueReceipts.reduce((sum, r) => sum + (r.invoice_amount || 0), 0),
    }
  }, [rawData?.receipts])

  // Client-side filtering for ALL filters (status, type, person, payment, reimbursementOverdue)
  // This ensures rawData.total always reflects the true unfiltered total
  const data = rawData ? {
    ...rawData,
    receipts: rawData.receipts.filter((receipt) => {
      // Status filter
      if (statusFilter && receipt.status !== statusFilter) return false

      // Type filter
      if (typeFilter && receipt.receipt_type !== typeFilter) return false

      // Person filter
      if (person && !receipt.insured_person?.toLowerCase().includes(person.toLowerCase())) return false

      // Reimbursement overdue filter (separate from payment filter)
      if (reimbursementOverdue) {
        const todayMidnight = new Date()
        todayMidnight.setHours(0, 0, 0, 0)
        const submissionDate = receipt.submission_date ? new Date(receipt.submission_date) : null
        const daysSinceSubmission = submissionDate
          ? Math.floor((todayMidnight.getTime() - submissionDate.getTime()) / (1000 * 60 * 60 * 24))
          : 0
        const isReimbursementOverdue = receipt.status === 'submitted' && daysSinceSubmission > 30
        if (!isReimbursementOverdue) return false
      }

      // Payment filter
      if (!paymentFilter) return true

      const isPaid = receipt.paid_date || receipt.receipt_type === 'rezept'
      const todayMidnight = new Date()
      todayMidnight.setHours(0, 0, 0, 0)
      const isPaymentOverdue = receipt.due_date && new Date(receipt.due_date) < todayMidnight && !isPaid

      switch (paymentFilter) {
        case 'paid': return isPaid
        case 'unpaid': return !isPaid && receipt.receipt_type !== 'rezept'
        case 'overdue': return isPaymentOverdue
        default: return true
      }
    })
  } : null

  const handleUpload = async (file: File) => {
    setUploading(true)
    setMessage(null)
    try {
      const result = await receiptsApi.upload(file)
      setMessage({
        type: 'success',
        text: `${result.message} - Fällig: ${result.due_date ? formatDate(result.due_date) : 'unbekannt'}`,
      })
      queryClient.invalidateQueries({ queryKey: ['receipts'] })
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Upload fehlgeschlagen',
      })
    } finally {
      setUploading(false)
    }
  }

  const handleMatchSettlements = async () => {
    setMatching(true)
    setMessage(null)
    try {
      const result = await receiptsApi.matchSettlements()
      setMessage({
        type: 'success',
        text: `${result.matched} Belege mit Erstattungen verknüpft`,
      })
      queryClient.invalidateQueries({ queryKey: ['receipts'] })
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Abgleich fehlgeschlagen',
      })
    } finally {
      setMatching(false)
    }
  }

  const handleMatchPayments = async () => {
    setMatchingPayments(true)
    setMessage(null)
    try {
      const result = await receiptsApi.matchPayments()
      setMessage({
        type: 'success',
        text: `${result.matched} von ${result.checked} Belegen mit Bankzahlungen verknüpft`,
      })
      queryClient.invalidateQueries({ queryKey: ['receipts'] })
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Abgleich fehlgeschlagen',
      })
    } finally {
      setMatchingPayments(false)
    }
  }

  const handleSavePaymentLink = async (
    receiptId: string,
    transactionId: string | null,
    paidDate: string | null,
    forceUnlink = false
  ): Promise<{ success: boolean; conflict?: SuggestedTransactionLinkedInfo }> => {
    try {
      await receiptsApi.update(receiptId, {
        payment_transaction_id: transactionId,
        paid_date: paidDate,
        force_unlink_payment: forceUnlink,
      } as Partial<Receipt> & { force_unlink_payment?: boolean })
      setMessage({
        type: 'success',
        text: transactionId
          ? forceUnlink
            ? 'Zahlung neu zugeordnet (vorherige Verknüpfung gelöst)'
            : 'Zahlung verknüpft'
          : 'Verknüpfung entfernt',
      })
      queryClient.invalidateQueries({ queryKey: ['receipts'] })
      setPaymentLinkReceipt(null)
      return { success: true }
    } catch (err) {
      // Check for 409 conflict (payment already linked)
      if (err instanceof Error && err.message.startsWith('409:')) {
        try {
          // Parse the JSON after "409: "
          const jsonStr = err.message.slice(5)
          const errorData = JSON.parse(jsonStr)
          if (errorData.linked_receipt) {
            return { success: false, conflict: errorData.linked_receipt }
          }
        } catch {
          // If parsing fails, just return a generic conflict
        }
        return {
          success: false,
          conflict: {
            receipt_id: 'unknown',
            provider_name: 'Anderer Beleg',
            invoice_amount: null,
            invoice_date: null,
          },
        }
      }

      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Speichern fehlgeschlagen',
      })
      return { success: false }
    }
  }

  const handleUnlinkReimbursement = async (receipt: Receipt) => {
    try {
      await receiptsApi.update(receipt.id, {
        settlement_item_id: null,
      } as Partial<Receipt>)
      setMessage({
        type: 'success',
        text: 'Erstattungsverknüpfung gelöst',
      })
      queryClient.invalidateQueries({ queryKey: ['receipts'] })
      setUnlinkReimbursementReceipt(null)
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Fehler beim Lösen der Verknüpfung',
      })
    }
  }

  const handleLinkSettlement = async (
    receiptId: string,
    settlementItemId: string,
    reimbursedAmount: number | null,
    reimbursedDate: string | null
  ) => {
    try {
      await receiptsApi.update(receiptId, {
        settlement_item_id: settlementItemId,
        status: 'reimbursed',
        reimbursed_amount: reimbursedAmount,
        reimbursed_date: reimbursedDate,
        skip_date_check: true,  // Manual linking skips plausibility check
      } as Partial<Receipt> & { skip_date_check?: boolean })
      setMessage({
        type: 'success',
        text: 'Beleg mit Erstattung verknüpft',
      })
      queryClient.invalidateQueries({ queryKey: ['receipts'] })
      queryClient.invalidateQueries({ queryKey: ['unlinkedItems'] })
      setSettlementLinkReceipt(null)
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Fehler beim Verknüpfen',
      })
    }
  }

  const handleDeleteReceipt = async (receipt: Receipt) => {
    try {
      await receiptsApi.delete(receipt.id)
      setMessage({
        type: 'success',
        text: 'Beleg gelöscht',
      })
      queryClient.invalidateQueries({ queryKey: ['receipts'] })
      setDeleteReceipt(null)
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Fehler beim Löschen',
      })
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Eingereichte Belege</h1>
        <div className="flex gap-2">
          <button
            onClick={handleMatchPayments}
            disabled={matchingPayments}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 disabled:opacity-50"
            title="Belege mit Banküberweisungen abgleichen"
          >
            <CreditCard className={`h-4 w-4 ${matchingPayments ? 'animate-pulse' : ''}`} />
            Zahlungen abgleichen
          </button>
          <button
            onClick={handleMatchSettlements}
            disabled={matching}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 disabled:opacity-50"
            title="Belege mit PKV-Erstattungen abgleichen"
          >
            <RefreshCw className={`h-4 w-4 ${matching ? 'animate-spin' : ''}`} />
            Erstattungen abgleichen
          </button>
          <input
            type="file"
            ref={fileInputRef}
            accept=".pdf"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) {
                handleUpload(file)
                e.target.value = ''
              }
            }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            <Upload className={`h-4 w-4 ${uploading ? 'animate-pulse' : ''}`} />
            {uploading ? 'Wird verarbeitet...' : 'PDF hochladen'}
          </button>
        </div>
      </div>

      {/* Status Message */}
      {message && (
        <div className={`p-4 rounded-md ${message.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
          {message.text}
        </div>
      )}

      {/* Summary Stats - clickable to set filters */}
      {rawData && data && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {/* 1. Gesamt (always shows unfiltered total) */}
          <button
            onClick={() => { setStatusFilter(''); setReimbursementOverdue(false); setPaymentFilter(''); setTypeFilter(''); setPerson(''); }}
            className="bg-white rounded-lg shadow p-3 flex items-center gap-2 hover:ring-2 hover:ring-gray-300 transition text-left"
          >
            <div className="p-2 rounded-full bg-gray-500">
              <FileText className="h-4 w-4 text-white" />
            </div>
            <div>
              <p className="text-xs text-gray-500">Gesamt</p>
              <p className="text-lg font-semibold text-gray-900">
                {rawData.total}
                {statSums && <span className="text-xs font-normal text-gray-400 ml-1">({Math.round(statSums.total)}€)</span>}
              </p>
            </div>
          </button>
          {/* 2. Erstattung offen */}
          <button
            onClick={() => { setStatusFilter('submitted'); setReimbursementOverdue(false); setPaymentFilter(''); setTypeFilter(''); setPerson(''); }}
            className="bg-white rounded-lg shadow p-3 flex items-center gap-2 hover:ring-2 hover:ring-blue-300 transition text-left"
          >
            <div className="p-2 rounded-full bg-blue-500">
              <Clock className="h-4 w-4 text-white" />
            </div>
            <div>
              <p className="text-xs text-gray-500">Erstattung offen</p>
              <p className="text-lg font-semibold text-blue-600">
                {data.pending_count}
                {statSums && <span className="text-xs font-normal text-gray-400 ml-1">({Math.round(statSums.pending)}€)</span>}
              </p>
            </div>
          </button>
          {/* 3. Erstattung überfällig */}
          <button
            onClick={() => { setStatusFilter(''); setReimbursementOverdue(true); setPaymentFilter(''); setTypeFilter(''); setPerson(''); }}
            className="bg-white rounded-lg shadow p-3 flex items-center gap-2 hover:ring-2 hover:ring-orange-300 transition text-left"
          >
            <div className="p-2 rounded-full bg-orange-500">
              <AlertTriangle className="h-4 w-4 text-white" />
            </div>
            <div>
              <p className="text-xs text-gray-500">Erstattung überfällig</p>
              <p className="text-lg font-semibold text-orange-600">
                {data.reimbursement_overdue_count}
                {statSums && <span className="text-xs font-normal text-gray-400 ml-1">({Math.round(statSums.reimbursementOverdue)}€)</span>}
              </p>
            </div>
          </button>
          {/* 4. Unbezahlt */}
          <button
            onClick={() => { setStatusFilter(''); setReimbursementOverdue(false); setPaymentFilter('unpaid'); setTypeFilter(''); setPerson(''); }}
            className="bg-white rounded-lg shadow p-3 flex items-center gap-2 hover:ring-2 hover:ring-yellow-300 transition text-left"
          >
            <div className="p-2 rounded-full bg-yellow-500">
              <CreditCard className="h-4 w-4 text-white" />
            </div>
            <div>
              <p className="text-xs text-gray-500">Unbezahlt</p>
              <p className="text-lg font-semibold text-yellow-600">
                {data.unpaid_count}
                {statSums && <span className="text-xs font-normal text-gray-400 ml-1">({Math.round(statSums.unpaid)}€)</span>}
              </p>
            </div>
          </button>
          {/* 5. Zahlung überfällig */}
          <button
            onClick={() => { setStatusFilter(''); setReimbursementOverdue(false); setPaymentFilter('overdue'); setTypeFilter(''); setPerson(''); }}
            className="bg-white rounded-lg shadow p-3 flex items-center gap-2 hover:ring-2 hover:ring-red-300 transition text-left"
          >
            <div className="p-2 rounded-full bg-red-500">
              <AlertTriangle className="h-4 w-4 text-white" />
            </div>
            <div>
              <p className="text-xs text-gray-500">Zahlung überfällig</p>
              <p className="text-lg font-semibold text-red-600">
                {data.overdue_count}
                {statSums && <span className="text-xs font-normal text-gray-400 ml-1">({Math.round(statSums.paymentOverdue)}€)</span>}
              </p>
            </div>
          </button>
          {/* 6. Liqui Saldo */}
          <div
            className={`bg-white rounded-lg shadow p-3 flex items-center gap-2 ${data.liqui_saldo >= 0 ? 'ring-1 ring-green-200' : 'ring-1 ring-red-200'}`}
            title="Bezahlt aber noch nicht erstattet. Negativ = so viel Geld ist aktuell 'draußen'."
          >
            <div className={`p-2 rounded-full ${data.liqui_saldo >= 0 ? 'bg-green-500' : 'bg-red-500'}`}>
              <Banknote className="h-4 w-4 text-white" />
            </div>
            <div>
              <p className="text-xs text-gray-500">Liqui Saldo</p>
              <p className={`text-lg font-semibold ${data.liqui_saldo >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {data.liqui_saldo >= 0 ? '+' : ''}{formatCurrency(data.liqui_saldo)}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4 flex flex-wrap gap-4 items-end">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Erstattung</label>
          <select
            value={reimbursementOverdue ? 'overdue' : statusFilter}
            onChange={(e) => {
              const val = e.target.value
              if (val === 'overdue') {
                setStatusFilter('')
                setReimbursementOverdue(true)
              } else {
                setStatusFilter(val)
                setReimbursementOverdue(false)
              }
            }}
            className="border border-gray-300 rounded-md px-3 py-2 text-sm"
          >
            <option value="">Alle</option>
            <option value="submitted">Offen</option>
            <option value="overdue">Überfällig</option>
            <option value="reimbursed">Erstattet</option>
            <option value="rejected">Abgelehnt</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Typ</label>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="border border-gray-300 rounded-md px-3 py-2 text-sm"
          >
            <option value="">Alle</option>
            <option value="pflege">Pflege</option>
            <option value="rezept">Rezept</option>
            <option value="arzt">Arzt</option>
            <option value="hilfsmittel">Hilfsmittel</option>
            <option value="sonstige">Sonstige</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Zahlung</label>
          <select
            value={paymentFilter}
            onChange={(e) => setPaymentFilter(e.target.value)}
            className="border border-gray-300 rounded-md px-3 py-2 text-sm"
          >
            <option value="">Alle</option>
            <option value="paid">Bezahlt</option>
            <option value="unpaid">Unbezahlt</option>
            <option value="overdue">Überfällig</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Person</label>
          <input
            type="text"
            value={person}
            onChange={(e) => setPerson(e.target.value)}
            placeholder="Name..."
            className="border border-gray-300 rounded-md px-3 py-2 text-sm"
          />
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : error ? (
          <div className="p-6 text-center text-red-500">
            Fehler beim Laden: {error instanceof Error ? error.message : 'Unbekannt'}
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Eingereicht
                </th>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Typ
                </th>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Anbieter
                </th>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Person
                </th>
                <th className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Betrag
                </th>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Rechnung
                </th>
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Fällig
                </th>
                <th className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Zahlung
                </th>
                <th className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Erstattung
                </th>
                <th className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Aktion
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {data?.receipts.map((receipt) => (
                <tr key={receipt.id} className="hover:bg-gray-50">
                  <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-500">
                    {formatDate(receipt.submission_date)}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap">
                    {getReceiptTypeBadge(receipt.receipt_type)}
                  </td>
                  <td className="px-3 py-3 text-sm text-gray-900 max-w-xs">
                    <div className="truncate" title={receipt.provider_name || ''}>
                      {receipt.provider_name?.replace(/\s+/g, ' ').substring(0, 25) || '-'}
                    </div>
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-900">
                    {receipt.insured_person || '-'}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-900 text-right font-medium">
                    {formatCurrency(receipt.invoice_amount)}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-500">
                    {formatDate(receipt.invoice_date)}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-500">
                    {formatDate(receipt.due_date)}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-center">
                    {receipt.receipt_type === 'rezept' ? (
                      // Rezept: Direktzahlung, nicht klickbar
                      getPaymentBadge(receipt)
                    ) : receipt.paid_date && receipt.payment_transaction_id ? (
                      // Bezahlt mit Transaktions-Link: Details anzeigen
                      <button
                        onClick={() => setPaymentDetailReceipt(receipt)}
                        className="hover:opacity-80 transition cursor-pointer"
                        title="Zahlungsdetails anzeigen"
                      >
                        {getPaymentBadge(receipt)}
                      </button>
                    ) : !receipt.paid_date ? (
                      // Unbezahlt: QR-Modal öffnen
                      <button
                        onClick={() => setPaymentQRReceipt(receipt)}
                        className="hover:opacity-80 transition cursor-pointer"
                        title="QR-Code für Überweisung generieren"
                      >
                        {getPaymentBadge(receipt)}
                      </button>
                    ) : (
                      // Bezahlt ohne Transaktions-Link (manuell gesetzt)
                      getPaymentBadge(receipt)
                    )}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-center">
                    {getReimbursementBadge(receipt, true)}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-center">
                    <div className="flex items-center justify-center gap-1">
                      <button
                        onClick={() => setDetailReceipt(receipt)}
                        className="p-1 text-gray-400 hover:text-purple-600 hover:bg-purple-50 rounded"
                        title="Details & PDF anzeigen"
                      >
                        <Eye className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setPaymentLinkReceipt(receipt)}
                        className="p-1 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded"
                        title="Zahlung verknüpfen"
                      >
                        <CreditCard className="h-4 w-4" />
                      </button>
                      {/* Link/Unlink Erstattung - abhängig vom Status */}
                      {receipt.status === 'reimbursed' && receipt.settlement_item_id ? (
                        <button
                          onClick={() => setUnlinkReimbursementReceipt(receipt)}
                          className="p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded"
                          title="Erstattungsverknüpfung lösen"
                        >
                          <Unlink className="h-4 w-4" />
                        </button>
                      ) : !receipt.settlement_item_id && (
                        <button
                          onClick={() => setSettlementLinkReceipt(receipt)}
                          className="p-1 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded"
                          title="Mit Erstattung verknüpfen"
                        >
                          <Link2 className="h-4 w-4" />
                        </button>
                      )}
                      <button
                        onClick={() => setDeleteReceipt(receipt)}
                        className="p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded"
                        title="Beleg löschen"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {data?.receipts.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-3 py-8 text-center text-gray-500">
                    Keine Belege gefunden
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {data && (
        <p className="text-sm text-gray-500">
          {data.receipts.length} von {data.total} Belegen
        </p>
      )}

      {/* Payment Link Modal */}
      {paymentLinkReceipt && (
        <PaymentLinkModal
          receipt={paymentLinkReceipt}
          onClose={() => setPaymentLinkReceipt(null)}
          onSave={handleSavePaymentLink}
        />
      )}

      {/* Detail Modal with PDF */}
      {detailReceipt && (
        <ReceiptDetailModal
          receipt={detailReceipt}
          onClose={() => setDetailReceipt(null)}
        />
      )}

      {/* Correction Rule Dialog */}
      {correctionRuleDialog && (
        <CreateCorrectionRuleDialog
          fieldName={correctionRuleDialog.fieldName}
          oldValue={correctionRuleDialog.oldValue}
          newValue={correctionRuleDialog.newValue}
          onClose={() => setCorrectionRuleDialog(null)}
          onSave={() => {
            setMessage({
              type: 'success',
              text: 'Korrektur-Regel gespeichert',
            })
            setCorrectionRuleDialog(null)
          }}
        />
      )}

      {/* Unlink Reimbursement Confirmation Dialog */}
      {unlinkReimbursementReceipt && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex min-h-screen items-center justify-center p-4">
            <div className="fixed inset-0 bg-black/50" onClick={() => setUnlinkReimbursementReceipt(null)} />
            <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full">
              <div className="px-6 py-4 border-b bg-gray-50 rounded-t-lg">
                <h2 className="text-lg font-semibold text-gray-900">Erstattungsverknüpfung lösen?</h2>
              </div>

              <div className="px-6 py-4 space-y-4">
                <p className="text-sm text-gray-600">
                  Möchtest du die Verknüpfung zu dieser Erstattung wirklich lösen?
                </p>

                <div className="bg-gray-50 rounded-lg p-3 space-y-1 text-sm">
                  <div><span className="text-gray-500">Anbieter:</span> <span className="font-medium">{unlinkReimbursementReceipt.provider_name || '-'}</span></div>
                  <div><span className="text-gray-500">Betrag:</span> <span className="font-medium">{formatCurrency(unlinkReimbursementReceipt.invoice_amount)}</span></div>
                  <div><span className="text-gray-500">Abrechnung:</span> <span className="font-medium">{unlinkReimbursementReceipt.settlement_number || '-'}</span></div>
                  <div><span className="text-gray-500">Beleg:</span> <span className="font-medium">{unlinkReimbursementReceipt.receipt_number || '-'}</span></div>
                </div>

                <p className="text-xs text-gray-500">
                  Der Beleg wird wieder als "Wartet auf Erstattung" markiert.
                </p>
              </div>

              <div className="flex items-center justify-end gap-2 px-6 py-4 border-t bg-gray-50 rounded-b-lg">
                <button
                  onClick={() => setUnlinkReimbursementReceipt(null)}
                  className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md"
                >
                  Abbrechen
                </button>
                <button
                  onClick={() => handleUnlinkReimbursement(unlinkReimbursementReceipt)}
                  className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
                >
                  <Unlink className="h-4 w-4" />
                  Verknüpfung lösen
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Receipt Confirmation Dialog */}
      {deleteReceipt && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex min-h-screen items-center justify-center p-4">
            <div className="fixed inset-0 bg-black/50" onClick={() => setDeleteReceipt(null)} />
            <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full">
              <div className="px-6 py-4 border-b bg-gray-50 rounded-t-lg">
                <h2 className="text-lg font-semibold text-gray-900">Beleg löschen?</h2>
              </div>

              <div className="px-6 py-4 space-y-4">
                <p className="text-sm text-gray-600">
                  Möchtest du diesen Beleg wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.
                </p>

                <div className="bg-gray-50 rounded-lg p-3 space-y-1 text-sm">
                  <div><span className="text-gray-500">Anbieter:</span> <span className="font-medium">{deleteReceipt.provider_name || '-'}</span></div>
                  <div><span className="text-gray-500">Betrag:</span> <span className="font-medium">{formatCurrency(deleteReceipt.invoice_amount)}</span></div>
                  <div><span className="text-gray-500">Rechnungsdatum:</span> <span className="font-medium">{formatDate(deleteReceipt.invoice_date)}</span></div>
                  <div><span className="text-gray-500">Person:</span> <span className="font-medium">{deleteReceipt.insured_person || '-'}</span></div>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 px-6 py-4 border-t bg-gray-50 rounded-b-lg">
                <button
                  onClick={() => setDeleteReceipt(null)}
                  className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md"
                >
                  Abbrechen
                </button>
                <button
                  onClick={() => handleDeleteReceipt(deleteReceipt)}
                  className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
                >
                  <Trash2 className="h-4 w-4" />
                  Löschen
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Payment QR Code Modal */}
      {paymentQRReceipt && (
        <PaymentQRModal
          receipt={paymentQRReceipt}
          onClose={() => setPaymentQRReceipt(null)}
          onMarkPaid={() => {
            queryClient.invalidateQueries({ queryKey: ['receipts'] })
          }}
        />
      )}

      {/* Settlement Link Modal */}
      {settlementLinkReceipt && (
        <SettlementLinkModal
          receipt={settlementLinkReceipt}
          onClose={() => setSettlementLinkReceipt(null)}
          onSave={handleLinkSettlement}
        />
      )}

      {/* Payment Detail Modal */}
      {paymentDetailReceipt && (
        <PaymentDetailModal
          receipt={paymentDetailReceipt}
          onClose={() => setPaymentDetailReceipt(null)}
        />
      )}
    </div>
  )
}
