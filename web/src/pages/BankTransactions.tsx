import { useState, useRef, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { bankApi } from '../lib/api'
import { formatDate, formatCurrency } from '../lib/utils'
import { Upload, RefreshCw, CheckCircle, XCircle, ChevronLeft, ChevronRight, Search, X } from 'lucide-react'

const MONTHS = [
  'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
]

export default function BankTransactions() {
  const currentDate = new Date()
  const [universaOnly, setUniversaOnly] = useState(true)
  const [year, setYear] = useState<number>(currentDate.getFullYear())
  const [month, setMonth] = useState<number | undefined>(currentDate.getMonth() + 1)
  const [importing, setImporting] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const handleImport = async (file: File) => {
    setImporting(true)
    setMessage(null)
    try {
      const result = await bankApi.importCsv(file)
      setMessage({
        type: 'success',
        text: `Import erfolgreich: ${result.inserted} neu, ${result.skipped} übersprungen, ${result.matched} zugeordnet`,
      })
      queryClient.invalidateQueries({ queryKey: ['bankTransactions'] })
      queryClient.invalidateQueries({ queryKey: ['universaMatches'] })
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Import fehlgeschlagen',
      })
    } finally {
      setImporting(false)
    }
  }

  const handleUpdateLinks = async () => {
    setUpdating(true)
    setMessage(null)
    try {
      const result = await bankApi.updateLinks()
      setMessage({
        type: 'success',
        text: `${result.updated} Transaktionen neu zugeordnet`,
      })
      queryClient.invalidateQueries({ queryKey: ['bankTransactions'] })
      queryClient.invalidateQueries({ queryKey: ['universaMatches'] })
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Aktualisierung fehlgeschlagen',
      })
    } finally {
      setUpdating(false)
    }
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ['bankTransactions', universaOnly, year, month],
    queryFn: () => bankApi.transactions({
      limit: 500,
      universa_only: universaOnly,
      year,
      month,
    }),
  })

  // Navigation zwischen Monaten
  const goToPreviousMonth = () => {
    if (month === undefined) {
      setMonth(12)
      return
    }
    if (month === 1) {
      setMonth(12)
      setYear(year - 1)
    } else {
      setMonth(month - 1)
    }
  }

  const goToNextMonth = () => {
    if (month === undefined) {
      setMonth(1)
      return
    }
    if (month === 12) {
      setMonth(1)
      setYear(year + 1)
    } else {
      setMonth(month + 1)
    }
  }

  const { data: matches } = useQuery({
    queryKey: ['universaMatches'],
    queryFn: () => bankApi.universaMatches(),
  })

  // Filter transactions by search term (case-insensitive)
  const filteredTransactions = useMemo(() => {
    if (!data?.transactions) return []
    if (!searchTerm.trim()) return data.transactions

    const term = searchTerm.toLowerCase()
    return data.transactions.filter(tx =>
      tx.description.toLowerCase().includes(term)
    )
  }, [data?.transactions, searchTerm])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Banktransaktionen</h1>
        <div className="flex gap-2">
          <button
            onClick={handleUpdateLinks}
            disabled={updating}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${updating ? 'animate-spin' : ''}`} />
            Zuordnung aktualisieren
          </button>
          <input
            type="file"
            ref={fileInputRef}
            accept=".csv"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) {
                handleImport(file)
                e.target.value = ''
              }
            }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            <Upload className={`h-4 w-4 ${importing ? 'animate-pulse' : ''}`} />
            {importing ? 'Importiere...' : 'CSV importieren'}
          </button>
        </div>
      </div>

      {/* Status Message */}
      {message && (
        <div className={`p-4 rounded-md ${message.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
          {message.text}
        </div>
      )}

      {/* Universa Summary */}
      {matches && (
        <div className="bg-white rounded-lg shadow p-4">
          <h2 className="text-lg font-medium text-gray-900 mb-3">Universa-Zahlungen</h2>
          <div className="flex gap-8">
            <div className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-500" />
              <span className="text-sm text-gray-600">
                {matches.matched} zugeordnet
              </span>
            </div>
            <div className="flex items-center gap-2">
              <XCircle className="h-5 w-5 text-red-500" />
              <span className="text-sm text-gray-600">
                {matches.unmatched} offen
              </span>
            </div>
            <div className="text-sm text-gray-600">
              Gesamt: {matches.total} Zahlungen
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4 flex gap-4 items-center justify-between">
        {/* Monat/Jahr Picker */}
        <div className="flex items-center gap-2">
          <button
            onClick={goToPreviousMonth}
            className="p-2 hover:bg-gray-100 rounded-md"
            title="Vorheriger Monat"
          >
            <ChevronLeft className="h-5 w-5 text-gray-600" />
          </button>

          <div className="flex items-center gap-2">
            <select
              value={month || ''}
              onChange={(e) => setMonth(e.target.value ? parseInt(e.target.value) : undefined)}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm min-w-[120px]"
            >
              <option value="">Alle Monate</option>
              {MONTHS.map((m, idx) => (
                <option key={idx} value={idx + 1}>{m}</option>
              ))}
            </select>
            <select
              value={year}
              onChange={(e) => setYear(parseInt(e.target.value))}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm"
            >
              {[2024, 2025, 2026].map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>

          <button
            onClick={goToNextMonth}
            className="p-2 hover:bg-gray-100 rounded-md"
            title="Nächster Monat"
          >
            <ChevronRight className="h-5 w-5 text-gray-600" />
          </button>
        </div>

        {/* Search Field */}
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Beschreibung suchen..."
            className="w-full pl-9 pr-8 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
          />
          {searchTerm && (
            <button
              onClick={() => setSearchTerm('')}
              className="absolute right-2 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Universa Filter */}
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="universaOnly"
            checked={universaOnly}
            onChange={(e) => setUniversaOnly(e.target.checked)}
            className="h-4 w-4 text-blue-600 rounded"
          />
          <label htmlFor="universaOnly" className="text-sm text-gray-700">
            Nur Universa-Zahlungen
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
                  Datum
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Beschreibung
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Kategorie
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Betrag
                </th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredTransactions.map((tx) => (
                <tr key={tx.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {formatDate(tx.booking_date)}
                  </td>
                  <td
                    className="px-6 py-4 text-sm text-gray-900 max-w-md truncate cursor-help"
                    title={tx.description}
                  >
                    {tx.description.substring(0, 80)}
                    {tx.description.length > 80 && '...'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {tx.category || '-'}
                  </td>
                  <td className={`px-6 py-4 whitespace-nowrap text-sm font-medium text-right ${tx.amount >= 0 ? 'text-green-600' : 'text-gray-900'}`}>
                    {formatCurrency(tx.amount)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-center">
                    <div className="flex flex-col gap-1 items-center">
                      {/* Universa Settlement-Verknüpfung */}
                      {tx.is_universa_payment && (
                        tx.settlement_id ? (
                          <button
                            onClick={() => navigate(`/settlements?settlement=${tx.settlement_id}`)}
                            className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800 hover:bg-green-200 cursor-pointer"
                          >
                            Abrechnung →
                          </button>
                        ) : (
                          <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                            Offen
                          </span>
                        )
                      )}
                      {/* Receipt-Verknüpfung (bezahlte Rechnung) */}
                      {tx.linked_receipt && (
                        <button
                          onClick={() => navigate(`/receipts?receipt=${tx.linked_receipt!.id}`)}
                          className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 cursor-pointer"
                          title={`${tx.linked_receipt.provider_name || 'Beleg'} - ${tx.linked_receipt.invoice_amount?.toFixed(2) || '?'}€`}
                        >
                          {tx.linked_receipt.provider_name?.substring(0, 15) || 'Beleg'} →
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {data && (
        <div className="flex justify-between text-sm text-gray-500">
          <span>
            {searchTerm
              ? `${filteredTransactions.length} von ${data.total} Transaktionen`
              : `${data.total} Transaktionen`}
          </span>
          <span>Summe: {formatCurrency(data.total_amount)}</span>
        </div>
      )}
    </div>
  )
}
