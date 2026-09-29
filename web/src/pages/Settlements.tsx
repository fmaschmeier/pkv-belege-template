import { useState, useMemo, useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { settlementsApi, bankApi } from '../lib/api'
import type { Settlement, SettlementItem } from '../lib/api'
import { formatDate, formatCurrency } from '../lib/utils'
import { ChevronDown, ChevronRight, Upload, AlertTriangle, Eye, Pencil } from 'lucide-react'
import SettlementDetailModal from '../components/SettlementDetailModal'
import EditSettlementItemModal from '../components/EditSettlementItemModal'

// Calculate total_invoiced from items (using reimbursed_amount as fallback for Pflegegeld/Tagegeld)
function calculateTotalInvoiced(settlement: Settlement): number {
  return settlement.settlement_items.reduce((sum, item) => {
    const amount = item.invoice_amount ?? item.reimbursed_amount ?? 0
    return sum + amount
  }, 0)
}

interface SettlementRowProps {
  settlement: Settlement
  bankAmount: number | null
  onOpenDetail: (settlement: Settlement) => void
  onEditItem: (item: SettlementItem) => void
}

function SettlementRow({ settlement, bankAmount, onOpenDetail, onEditItem }: SettlementRowProps) {
  const [expanded, setExpanded] = useState(false)

  const totalInvoiced = calculateTotalInvoiced(settlement)
  const totalReimbursed = settlement.total_reimbursed ?? 0
  // Only warn about missing payment if there's actually something to reimburse
  const hasNoPayment = bankAmount === null && totalReimbursed > 0

  return (
    <>
      <tr
        className={`hover:bg-gray-50 ${hasNoPayment ? 'bg-yellow-50' : ''}`}
      >
        <td className="px-6 py-4 whitespace-nowrap">
          <div className="flex items-center">
            <button
              onClick={() => setExpanded(!expanded)}
              className="mr-2 p-1 hover:bg-gray-100 rounded"
            >
              {expanded ? (
                <ChevronDown className="h-4 w-4 text-gray-400" />
              ) : (
                <ChevronRight className="h-4 w-4 text-gray-400" />
              )}
            </button>
            <span className="text-sm font-medium text-gray-900">
              {settlement.settlement_number}
            </span>
            {hasNoPayment && (
              <span title="Keine Überweisung verknüpft">
                <AlertTriangle className="h-4 w-4 text-yellow-500 ml-2" />
              </span>
            )}
          </div>
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
          {formatDate(settlement.settlement_date)}
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
          {settlement.settlement_items.length} Positionen
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
          {formatCurrency(totalInvoiced)}
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-green-600">
          {formatCurrency(totalReimbursed)}
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
          {bankAmount !== null ? formatCurrency(bankAmount) : '-'}
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-center">
          <button
            onClick={() => onOpenDetail(settlement)}
            className="p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded"
            title="Details anzeigen"
          >
            <Eye className="h-4 w-4" />
          </button>
        </td>
      </tr>
      {expanded && settlement.settlement_items.map((item) => (
        <tr key={item.id} className="bg-gray-50">
          <td className="px-6 py-3 pl-12 text-sm text-gray-500">
            {item.receipt_number}
          </td>
          <td className="px-6 py-3 text-sm text-gray-500">
            {item.insured_person}
          </td>
          <td className="px-6 py-3 text-sm text-gray-500">
            {item.description}
            {item.notes && (
              <span className="ml-2 text-xs text-orange-600 cursor-help" title={item.notes}>
                ({item.notes.length > 50 ? item.notes.substring(0, 50) + '...' : item.notes})
              </span>
            )}
          </td>
          <td className="px-6 py-3 text-sm text-gray-500">
            {formatCurrency(item.invoice_amount ?? item.reimbursed_amount)}
          </td>
          <td className="px-6 py-3 text-sm font-medium text-green-600">
            {formatCurrency(item.reimbursed_amount)}
          </td>
          <td className="px-6 py-3"></td>
          <td className="px-6 py-3 text-center">
            <button
              onClick={() => onEditItem(item)}
              className="p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded"
              title="Position bearbeiten"
            >
              <Pencil className="h-4 w-4" />
            </button>
          </td>
        </tr>
      ))}
    </>
  )
}

export default function Settlements() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [year, setYear] = useState<number | undefined>()
  const [person, setPerson] = useState('')
  const [showNoPaymentOnly, setShowNoPaymentOnly] = useState(false)
  const [selectedSettlement, setSelectedSettlement] = useState<Settlement | null>(null)
  const [highlightItemId, setHighlightItemId] = useState<string | null>(null)
  const [editItem, setEditItem] = useState<SettlementItem | null>(null)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['settlements', year, person],
    queryFn: () => settlementsApi.list({ limit: 100, year, person: person || undefined }),
  })

  // Handle navigation from Items page via URL params
  useEffect(() => {
    const settlementId = searchParams.get('settlement')
    const itemId = searchParams.get('item')

    if (settlementId && data?.settlements) {
      const settlement = data.settlements.find(s => s.id === settlementId)
      if (settlement) {
        setSelectedSettlement(settlement)
        setHighlightItemId(itemId)
        // Clear URL params after opening
        setSearchParams({})
      }
    }
  }, [searchParams, data?.settlements, setSearchParams])

  // Fetch bank payments to match with settlements
  const { data: bankMatches } = useQuery({
    queryKey: ['universaMatches'],
    queryFn: () => bankApi.universaMatches(),
  })

  // Create a map of settlement_id -> bank amount
  const bankAmountBySettlement = useMemo(() => {
    const map = new Map<string, number>()
    if (bankMatches?.payments) {
      for (const payment of bankMatches.payments) {
        if (payment.settlement_id) {
          // Accumulate in case multiple payments for same settlement
          const existing = map.get(payment.settlement_id) ?? 0
          map.set(payment.settlement_id, existing + payment.amount)
        }
      }
    }
    return map
  }, [bankMatches])

  // Filter settlements based on selected filters
  const filteredSettlements = useMemo(() => {
    if (!data?.settlements) return []

    return data.settlements.filter((settlement) => {
      const bankAmount = bankAmountBySettlement.get(settlement.id)
      const totalReimbursed = settlement.total_reimbursed ?? 0
      // Only consider "no payment" if there's actually something to reimburse
      const hasNoPayment = bankAmount === undefined && totalReimbursed > 0

      // If no filter is active, show all
      if (!showNoPaymentOnly) return true

      // Filter: Ohne Überweisung
      if (showNoPaymentOnly && hasNoPayment) return true

      return false
    })
  }, [data?.settlements, showNoPaymentOnly, bankAmountBySettlement])

  // Calculate totals for settlements without bank payment (only those with actual reimbursement)
  const missingPaymentsTotal = useMemo(() => {
    return data?.settlements
      .filter((s) => !bankAmountBySettlement.has(s.id) && (s.total_reimbursed ?? 0) > 0)
      .reduce((sum, s) => sum + (s.total_reimbursed ?? 0), 0) ?? 0
  }, [data?.settlements, bankAmountBySettlement])

  const years = [2024, 2025, 2026]

  const handleUpload = async (file: File) => {
    setUploading(true)
    setMessage(null)
    try {
      const result = await settlementsApi.upload(file)
      setMessage({
        type: 'success',
        text: `${result.settlement_number} erfolgreich importiert`,
      })
      queryClient.invalidateQueries({ queryKey: ['settlements'] })
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Upload fehlgeschlagen',
      })
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Leistungsabrechnungen</h1>
        <div>
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
            {uploading ? 'Wird hochgeladen...' : 'PDF hochladen'}
          </button>
        </div>
      </div>

      {/* Message */}
      {message && (
        <div className={`p-4 rounded-md ${message.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
          {message.text}
        </div>
      )}

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4 flex flex-wrap gap-4 items-end">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Jahr</label>
          <select
            value={year || ''}
            onChange={(e) => setYear(e.target.value ? parseInt(e.target.value) : undefined)}
            className="border border-gray-300 rounded-md px-3 py-2 text-sm"
          >
            <option value="">Alle</option>
            {years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
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
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="noPayment"
            checked={showNoPaymentOnly}
            onChange={(e) => setShowNoPaymentOnly(e.target.checked)}
            className="h-4 w-4 text-yellow-600 border-gray-300 rounded"
          />
          <label htmlFor="noPayment" className="text-sm text-gray-700">
            Ohne Überweisung
          </label>
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
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Abrechnung
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Datum
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Positionen
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Rechnungsbetrag
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Erstattet
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Überweisung
                </th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Aktion
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredSettlements.map((settlement) => (
                <SettlementRow
                  key={settlement.id}
                  settlement={settlement}
                  bankAmount={bankAmountBySettlement.get(settlement.id) ?? null}
                  onOpenDetail={setSelectedSettlement}
                  onEditItem={setEditItem}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {data && (
        <div className="text-sm text-gray-500 space-y-1">
          <p>
            {filteredSettlements.length} von {data.total} Abrechnungen
            {showNoPaymentOnly && ' (ohne Überweisung)'}
          </p>
          {missingPaymentsTotal > 0 && (
            <p className="text-yellow-600">
              Offene Überweisungen: {formatCurrency(missingPaymentsTotal)}
            </p>
          )}
        </div>
      )}

      {/* Settlement Detail Modal */}
      {selectedSettlement && (
        <SettlementDetailModal
          settlement={selectedSettlement}
          highlightItemId={highlightItemId}
          onClose={() => {
            setSelectedSettlement(null)
            setHighlightItemId(null)
          }}
        />
      )}

      {/* Edit Item Modal */}
      {editItem && (
        <EditSettlementItemModal
          item={editItem}
          onClose={() => setEditItem(null)}
        />
      )}
    </div>
  )
}
