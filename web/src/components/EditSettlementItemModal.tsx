import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { settlementsApi } from '../lib/api'
import type { SettlementItem } from '../lib/api'
import { formatCurrency } from '../lib/utils'
import { X, CheckCircle } from 'lucide-react'

interface EditSettlementItemModalProps {
  item: SettlementItem
  onClose: () => void
  onSaved?: () => void
}

export default function EditSettlementItemModal({
  item,
  onClose,
  onSaved,
}: EditSettlementItemModalProps) {
  const [description, setDescription] = useState(item.description || '')
  const [invoiceAmount, setInvoiceAmount] = useState(item.invoice_amount?.toString() || '')
  const [reimbursedAmount, setReimbursedAmount] = useState(item.reimbursed_amount?.toString() || '')
  const [treatmentPeriod, setTreatmentPeriod] = useState(item.treatment_period || '')
  const [insuredPerson, setInsuredPerson] = useState(item.insured_person || '')
  const [notes, setNotes] = useState(
    Array.isArray(item.notes) ? item.notes.join(' | ') : (item.notes || '')
  )
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const queryClient = useQueryClient()

  const handleSave = async () => {
    setSaving(true)
    setMessage(null)

    const updates: Partial<SettlementItem> = {}

    if (description !== (item.description || '')) {
      updates.description = description
    }
    if (invoiceAmount !== (item.invoice_amount?.toString() || '')) {
      updates.invoice_amount = parseFloat(invoiceAmount) || 0
    }
    if (reimbursedAmount !== (item.reimbursed_amount?.toString() || '')) {
      updates.reimbursed_amount = parseFloat(reimbursedAmount) || 0
    }
    if (treatmentPeriod !== (item.treatment_period || '')) {
      updates.treatment_period = treatmentPeriod
    }
    if (insuredPerson !== (item.insured_person || '')) {
      updates.insured_person = insuredPerson
    }
    const originalNotes = Array.isArray(item.notes) ? item.notes.join(' | ') : (item.notes || '')
    if (notes !== originalNotes) {
      updates.notes = notes || null
    }

    if (Object.keys(updates).length === 0) {
      onClose()
      return
    }

    try {
      await settlementsApi.updateItem(item.id, updates)
      setMessage({ type: 'success', text: 'Position aktualisiert' })
      queryClient.invalidateQueries({ queryKey: ['settlements'] })
      queryClient.invalidateQueries({ queryKey: ['items'] })
      setTimeout(() => {
        onSaved?.()
        onClose()
      }, 500)
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Speichern fehlgeschlagen',
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        {/* Backdrop */}
        <div className="fixed inset-0 bg-black/50" onClick={onClose} />

        {/* Modal */}
        <div className="relative bg-white rounded-lg shadow-xl max-w-lg w-full">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b bg-gray-50 rounded-t-lg">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Position bearbeiten</h2>
              <p className="text-sm text-gray-500">{item.receipt_number}</p>
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Message */}
          {message && (
            <div className={`mx-6 mt-4 p-3 rounded-md ${message.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
              {message.text}
            </div>
          )}

          {/* Content */}
          <div className="px-6 py-4 space-y-4">
            {/* Beschreibung */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Beschreibung</label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
                placeholder="z.B. Ergotherapie"
              />
            </div>

            {/* Person */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Versicherte Person</label>
              <input
                type="text"
                value={insuredPerson}
                onChange={(e) => setInsuredPerson(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            {/* Zeitraum */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Behandlungszeitraum</label>
              <input
                type="text"
                value={treatmentPeriod}
                onChange={(e) => setTreatmentPeriod(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
                placeholder="z.B. 01.01.-31.03.2025"
              />
            </div>

            {/* Beträge */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Rechnungsbetrag (EUR)</label>
                <input
                  type="number"
                  step="0.01"
                  value={invoiceAmount}
                  onChange={(e) => setInvoiceAmount(e.target.value)}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Erstattung (EUR)</label>
                <input
                  type="number"
                  step="0.01"
                  value={reimbursedAmount}
                  onChange={(e) => setReimbursedAmount(e.target.value)}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
            </div>

            {/* Anmerkungen */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Anmerkungen der PKV</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={3}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
                placeholder="z.B. Ablehnung wegen fehlender Unterlagen..."
              />
            </div>

            {/* Info: Aktuell vs Neu */}
            <div className="bg-gray-50 rounded-lg p-3 text-xs text-gray-500">
              <div className="flex justify-between">
                <span>Aktuell: {formatCurrency(item.invoice_amount)} / {formatCurrency(item.reimbursed_amount)}</span>
                <span>Differenz: {formatCurrency((item.invoice_amount || 0) - (item.reimbursed_amount || 0))}</span>
              </div>
            </div>
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
              disabled={saving}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
              ) : (
                <CheckCircle className="h-4 w-4" />
              )}
              Speichern
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
