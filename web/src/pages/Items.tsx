import { useState, useMemo, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useLocation } from 'react-router-dom'
import { itemsApi } from '../lib/api'
import type { ItemWithSettlement } from '../lib/api'
import { formatDate, formatCurrency } from '../lib/utils'
import { Receipt, Euro, AlertTriangle, Eye, Pencil } from 'lucide-react'
import EditSettlementItemModal from '../components/EditSettlementItemModal'
import type { SettlementItem } from '../lib/api'

// Bei Pflegegeld/Tagegeld ist invoice_amount null - dann reimbursed_amount verwenden
function getInvoiceAmount(item: { invoice_amount: number | null, reimbursed_amount: number | null }): number | null {
  return item.invoice_amount ?? item.reimbursed_amount
}

// Prüft ob Rechnungsbetrag und Erstattungsbetrag unterschiedlich sind
function hasDifference(item: ItemWithSettlement): boolean {
  const invoiceAmount = getInvoiceAmount(item) ?? 0
  const reimbursedAmount = item.reimbursed_amount ?? 0
  return Math.abs(invoiceAmount - reimbursedAmount) > 0.01
}

export default function Items() {
  const navigate = useNavigate()
  const location = useLocation()
  const [year, setYear] = useState<number | undefined>()
  const [month, setMonth] = useState<number | undefined>()
  const [person, setPerson] = useState('')
  const [showDifferencesOnly, setShowDifferencesOnly] = useState(false)
  const [editItem, setEditItem] = useState<SettlementItem | null>(null)
  const [highlightedItemId, setHighlightedItemId] = useState<string | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['items', year, month, person],
    queryFn: () => itemsApi.list({
      limit: 500,
      year,
      month,
      person: person || undefined,
    }),
  })

  // Handle URL hash for scrolling to specific item
  useEffect(() => {
    if (location.hash && data?.items) {
      const itemId = location.hash.replace('#item-', '')
      setHighlightedItemId(itemId)

      // Wait for DOM to update, then scroll
      setTimeout(() => {
        const element = document.getElementById(`item-${itemId}`)
        if (element) {
          element.scrollIntoView({ behavior: 'smooth', block: 'center' })
          // Remove highlight after 3 seconds
          setTimeout(() => setHighlightedItemId(null), 3000)
        }
      }, 100)
    }
  }, [location.hash, data?.items])

  // Filter items based on difference filter
  const filteredItems = useMemo(() => {
    if (!data?.items) return []
    if (!showDifferencesOnly) return data.items
    return data.items.filter(hasDifference)
  }, [data?.items, showDifferencesOnly])

  // Count items with differences
  const differenceCount = useMemo(() => {
    if (!data?.items) return 0
    return data.items.filter(hasDifference).length
  }, [data?.items])

  const years = [2024, 2025, 2026]
  const months = [
    { value: 1, label: 'Januar' },
    { value: 2, label: 'Februar' },
    { value: 3, label: 'März' },
    { value: 4, label: 'April' },
    { value: 5, label: 'Mai' },
    { value: 6, label: 'Juni' },
    { value: 7, label: 'Juli' },
    { value: 8, label: 'August' },
    { value: 9, label: 'September' },
    { value: 10, label: 'Oktober' },
    { value: 11, label: 'November' },
    { value: 12, label: 'Dezember' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Belege</h1>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow p-4 flex items-center gap-4">
          <div className="p-3 rounded-full bg-blue-500">
            <Receipt className="h-6 w-6 text-white" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Anzahl Belege</p>
            <p className="text-2xl font-semibold text-gray-900">{data?.total || 0}</p>
          </div>
        </div>
        <div className="bg-white rounded-lg shadow p-4 flex items-center gap-4">
          <div className="p-3 rounded-full bg-gray-500">
            <Euro className="h-6 w-6 text-white" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Summe Rechnungen</p>
            <p className="text-2xl font-semibold text-gray-900">{formatCurrency(data?.total_invoiced || 0)}</p>
          </div>
        </div>
        <div className="bg-white rounded-lg shadow p-4 flex items-center gap-4">
          <div className="p-3 rounded-full bg-green-500">
            <Euro className="h-6 w-6 text-white" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Summe erstattet</p>
            <p className="text-2xl font-semibold text-green-600">{formatCurrency(data?.total_reimbursed || 0)}</p>
          </div>
        </div>
        <div className="bg-white rounded-lg shadow p-4 flex items-center gap-4">
          <div className="p-3 rounded-full bg-orange-500">
            <Euro className="h-6 w-6 text-white" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Nicht erstattet</p>
            <p className="text-2xl font-semibold text-orange-600">{formatCurrency((data?.total_invoiced || 0) - (data?.total_reimbursed || 0))}</p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4 flex flex-wrap gap-4 items-end">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Jahr</label>
          <select
            value={year || ''}
            onChange={(e) => {
              setYear(e.target.value ? parseInt(e.target.value) : undefined)
              if (!e.target.value) setMonth(undefined)
            }}
            className="border border-gray-300 rounded-md px-3 py-2 text-sm"
          >
            <option value="">Alle</option>
            {years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Monat</label>
          <select
            value={month || ''}
            onChange={(e) => setMonth(e.target.value ? parseInt(e.target.value) : undefined)}
            disabled={!year}
            className="border border-gray-300 rounded-md px-3 py-2 text-sm disabled:opacity-50"
          >
            <option value="">Alle</option>
            {months.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
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
            id="withDifference"
            checked={showDifferencesOnly}
            onChange={(e) => setShowDifferencesOnly(e.target.checked)}
            className="h-4 w-4 text-orange-600 border-gray-300 rounded"
          />
          <label htmlFor="withDifference" className="text-sm text-gray-700">
            Mit Differenz {differenceCount > 0 && `(${differenceCount})`}
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
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Beleg
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Datum
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Person
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Beschreibung
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Zeitraum
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Rechnung
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Erstattet
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Aktion
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredItems.map((item) => {
                const itemHasDiff = hasDifference(item)
                return (
                  <tr
                    key={item.id}
                    id={`item-${item.id}`}
                    className={`hover:bg-gray-50 ${itemHasDiff ? 'bg-orange-50' : ''} ${highlightedItemId === item.id ? 'ring-2 ring-blue-500 ring-inset bg-blue-50' : ''}`}
                  >
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex items-center">
                        <div>
                          <div className="text-sm font-medium text-gray-900">{item.receipt_number}</div>
                          <div className="text-xs text-gray-500">{item.settlement_number}</div>
                        </div>
                        {itemHasDiff && (
                          <span title="Differenz zwischen Rechnung und Erstattung">
                            <AlertTriangle className="h-4 w-4 text-orange-500 ml-2" />
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                      {formatDate(item.settlement_date)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                      {item.insured_person || '-'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900 max-w-xs">
                      <div className="truncate">{item.description || '-'}</div>
                      {item.notes && (
                        <div className="text-xs text-orange-600 truncate cursor-help" title={item.notes}>({item.notes})</div>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                      {item.treatment_period || '-'}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 text-right">
                      {formatCurrency(getInvoiceAmount(item))}
                    </td>
                    <td className={`px-4 py-3 whitespace-nowrap text-sm font-medium text-right ${itemHasDiff ? 'text-orange-600' : 'text-green-600'}`}>
                      {formatCurrency(item.reimbursed_amount)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-center">
                      <div className="flex items-center justify-center gap-1">
                        <button
                          onClick={() => navigate(`/settlements?settlement=${item.settlement_id}&item=${item.id}`)}
                          className="p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded"
                          title="Zur Leistungsabrechnung"
                        >
                          <Eye className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => setEditItem(item as SettlementItem)}
                          className="p-1 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded"
                          title="Position bearbeiten"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {data && (
        <p className="text-sm text-gray-500">
          {filteredItems.length} von {data.total} Belegen
          {showDifferencesOnly && ' (mit Differenz)'}
        </p>
      )}

      {/* Edit Modal */}
      {editItem && (
        <EditSettlementItemModal
          item={editItem}
          onClose={() => setEditItem(null)}
        />
      )}
    </div>
  )
}
