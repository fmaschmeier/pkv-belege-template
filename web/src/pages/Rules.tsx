import { useState, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { rulesApi } from '../lib/api'
import type { CorrectionRule, MatchingRule, ProviderPaymentInfo } from '../lib/api'
import { formatDate } from '../lib/utils'
import { Plus, Pencil, Trash2, X, CheckCircle, Info, Settings, Link2, CreditCard, HelpCircle } from 'lucide-react'

type TabType = 'corrections' | 'matching' | 'bankinfo'

// Tooltip component for column headers - uses fixed positioning to escape overflow containers
function ColumnHeader({ label, tooltip }: { label: string; tooltip: string }) {
  const [showTooltip, setShowTooltip] = useState(false)
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const iconRef = useRef<HTMLDivElement>(null)

  const handleMouseEnter = () => {
    if (iconRef.current) {
      const rect = iconRef.current.getBoundingClientRect()
      setPosition({ x: rect.left + rect.width / 2, y: rect.top })
      setShowTooltip(true)
    }
  }

  return (
    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
      <div className="flex items-center gap-1">
        {label}
        <div
          ref={iconRef}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={() => setShowTooltip(false)}
          className="cursor-help"
        >
          <HelpCircle className="h-3.5 w-3.5 text-gray-400" />
        </div>
        {showTooltip && (
          <div
            className="fixed px-3 py-2 bg-gray-900 text-white text-xs rounded-lg whitespace-normal w-48 shadow-lg pointer-events-none"
            style={{
              left: position.x,
              top: position.y,
              transform: 'translate(-50%, -100%) translateY(-8px)',
              zIndex: 9999
            }}
          >
            {tooltip}
            <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900"></div>
          </div>
        )}
      </div>
    </th>
  )
}

// === Correction Rule Modal ===
function CorrectionRuleModal({
  rule,
  onClose,
  onSave,
}: {
  rule: CorrectionRule | null
  onClose: () => void
  onSave: (data: Partial<CorrectionRule>) => Promise<void>
}) {
  const [fieldName, setFieldName] = useState(rule?.field_name || 'provider_name')
  const [rawValue, setRawValue] = useState(rule?.raw_value || '')
  const [correctedValue, setCorrectedValue] = useState(rule?.corrected_value || '')
  const [active, setActive] = useState(rule?.active ?? true)
  const [description, setDescription] = useState(rule?.description || '')
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    await onSave({
      field_name: fieldName,
      raw_value: rawValue,
      corrected_value: correctedValue,
      active,
      description: description || null,
    })
    setSaving(false)
  }

  const fieldOptions = [
    { value: 'provider_name', label: 'Anbieter' },
    { value: 'insured_person', label: 'Versicherte Person' },
    { value: 'description', label: 'Beschreibung' },
  ]

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        <div className="fixed inset-0 bg-black/50" onClick={onClose} />
        <div className="relative bg-white rounded-lg shadow-xl max-w-lg w-full">
          <div className="flex items-center justify-between px-6 py-4 border-b bg-gray-50 rounded-t-lg">
            <h2 className="text-lg font-semibold text-gray-900">
              {rule ? 'Korrektur-Regel bearbeiten' : 'Neue Korrektur-Regel'}
            </h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="px-6 py-4 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Feld</label>
              <select
                value={fieldName}
                onChange={(e) => setFieldName(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
              >
                {fieldOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Original-Wert (vom Parser)
              </label>
              <input
                type="text"
                value={rawValue}
                onChange={(e) => setRawValue(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                placeholder="z.B. Dr. Müller Praxis"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Korrigierter Wert
              </label>
              <input
                type="text"
                value={correctedValue}
                onChange={(e) => setCorrectedValue(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                placeholder="z.B. PVS Kinderarzt"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Beschreibung (optional)
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                placeholder="z.B. OCR-Korrektur"
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="active"
                checked={active}
                onChange={(e) => setActive(e.target.checked)}
                className="h-4 w-4 text-blue-600 border-gray-300 rounded"
              />
              <label htmlFor="active" className="text-sm text-gray-700">Aktiv</label>
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 px-6 py-4 border-t bg-gray-50 rounded-b-lg">
            <button onClick={onClose} className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md">
              Abbrechen
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !rawValue || !correctedValue}
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

// === Matching Rule Modal ===
function MatchingRuleModal({
  rule,
  onClose,
  onSave,
}: {
  rule: MatchingRule | null
  onClose: () => void
  onSave: (data: Partial<MatchingRule>) => Promise<void>
}) {
  const [providerPattern, setProviderPattern] = useState(rule?.provider_pattern || '')
  const [bankPatterns, setBankPatterns] = useState(rule?.bank_patterns?.join(', ') || '')
  const [matchType, setMatchType] = useState(rule?.match_type || 'provider')
  const [priority, setPriority] = useState(rule?.priority?.toString() || '0')
  const [active, setActive] = useState(rule?.active ?? true)
  const [description, setDescription] = useState(rule?.description || '')
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    await onSave({
      provider_pattern: providerPattern,
      bank_patterns: bankPatterns.split(',').map((p) => p.trim()).filter(Boolean),
      match_type: matchType,
      priority: parseInt(priority) || 0,
      active,
      description: description || null,
    })
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        <div className="fixed inset-0 bg-black/50" onClick={onClose} />
        <div className="relative bg-white rounded-lg shadow-xl max-w-lg w-full">
          <div className="flex items-center justify-between px-6 py-4 border-b bg-gray-50 rounded-t-lg">
            <h2 className="text-lg font-semibold text-gray-900">
              {rule ? 'Matching-Regel bearbeiten' : 'Neue Matching-Regel'}
            </h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="px-6 py-4 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Provider-Pattern (im Beleg)
              </label>
              <input
                type="text"
                value={providerPattern}
                onChange={(e) => setProviderPattern(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                placeholder="z.B. LEBENSHILFE"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Bank-Patterns (kommagetrennt)
              </label>
              <input
                type="text"
                value={bankPatterns}
                onChange={(e) => setBankPatterns(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                placeholder="z.B. FED MUSTERSTADT, ENTLASTUNG"
              />
              <p className="text-xs text-gray-500 mt-1">
                Wird in der Bank-Transaktion gesucht (case-insensitive)
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Match-Typ</label>
              <select
                value={matchType}
                onChange={(e) => setMatchType(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
              >
                <option value="provider">Standard (Betrag + Provider)</option>
                <option value="verhinderungspflege">Verhinderungspflege (+ Datum)</option>
              </select>
              <p className="text-xs text-gray-500 mt-1">
                Verhinderungspflege prüft zusätzlich das Leistungsdatum
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Priorität</label>
              <input
                type="number"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                placeholder="0"
              />
              <p className="text-xs text-gray-500 mt-1">
                Höhere Priorität wird zuerst geprüft
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Beschreibung (optional)
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                placeholder="z.B. Verhinderungspflege Lebenshilfe"
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="active"
                checked={active}
                onChange={(e) => setActive(e.target.checked)}
                className="h-4 w-4 text-blue-600 border-gray-300 rounded"
              />
              <label htmlFor="active" className="text-sm text-gray-700">Aktiv</label>
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 px-6 py-4 border-t bg-gray-50 rounded-b-lg">
            <button onClick={onClose} className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md">
              Abbrechen
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !providerPattern || !bankPatterns}
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

// === Payment Info Modal ===
function PaymentInfoModal({
  info,
  onClose,
  onSave,
}: {
  info: ProviderPaymentInfo | null
  onClose: () => void
  onSave: (data: Partial<ProviderPaymentInfo>) => Promise<void>
}) {
  const [providerPattern, setProviderPattern] = useState(info?.provider_pattern || '')
  const [paymentRecipient, setPaymentRecipient] = useState(info?.payment_recipient || '')
  const [paymentIban, setPaymentIban] = useState(info?.payment_iban || '')
  const [active, setActive] = useState(info?.active ?? true)
  const [saving, setSaving] = useState(false)

  // Format IBAN with spaces for display
  const formatIban = (value: string) => {
    const clean = value.replace(/\s/g, '').toUpperCase()
    return clean.replace(/(.{4})/g, '$1 ').trim()
  }

  const handleSave = async () => {
    setSaving(true)
    await onSave({
      provider_pattern: providerPattern,
      payment_recipient: paymentRecipient || null,
      payment_iban: paymentIban.replace(/\s/g, '') || null,
      active,
    })
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        <div className="fixed inset-0 bg-black/50" onClick={onClose} />
        <div className="relative bg-white rounded-lg shadow-xl max-w-lg w-full">
          <div className="flex items-center justify-between px-6 py-4 border-b bg-gray-50 rounded-t-lg">
            <h2 className="text-lg font-semibold text-gray-900">
              {info ? 'Bankverbindung bearbeiten' : 'Neue Bankverbindung'}
            </h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="px-6 py-4 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Anbieter-Pattern
              </label>
              <input
                type="text"
                value={providerPattern}
                onChange={(e) => setProviderPattern(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                placeholder="z.B. LEBENSHILFE"
              />
              <p className="text-xs text-gray-500 mt-1">
                Matcht wenn dieser Text im Anbieternamen des Belegs enthalten ist (Teilstring, Groß-/Kleinschreibung egal)
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Empfänger
              </label>
              <input
                type="text"
                value={paymentRecipient}
                onChange={(e) => setPaymentRecipient(e.target.value)}
                maxLength={70}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                placeholder="z.B. Familienentlastender Dienst Musterstadt e.V."
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                IBAN
              </label>
              <input
                type="text"
                value={formatIban(paymentIban)}
                onChange={(e) => setPaymentIban(e.target.value.replace(/\s/g, ''))}
                maxLength={42}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm font-mono"
                placeholder="DE89 3704 0044 0532 0130 00"
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="active"
                checked={active}
                onChange={(e) => setActive(e.target.checked)}
                className="h-4 w-4 text-blue-600 border-gray-300 rounded"
              />
              <label htmlFor="active" className="text-sm text-gray-700">Aktiv</label>
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 px-6 py-4 border-t bg-gray-50 rounded-b-lg">
            <button onClick={onClose} className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md">
              Abbrechen
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !providerPattern}
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

// === Main Component ===
export default function Rules() {
  const [activeTab, setActiveTab] = useState<TabType>('corrections')
  const [editCorrectionRule, setEditCorrectionRule] = useState<CorrectionRule | null>(null)
  const [editMatchingRule, setEditMatchingRule] = useState<MatchingRule | null>(null)
  const [editPaymentInfo, setEditPaymentInfo] = useState<ProviderPaymentInfo | null>(null)
  const [showNewCorrectionModal, setShowNewCorrectionModal] = useState(false)
  const [showNewMatchingModal, setShowNewMatchingModal] = useState(false)
  const [showNewPaymentInfoModal, setShowNewPaymentInfoModal] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [duplicateConflict, setDuplicateConflict] = useState<{
    type: 'duplicate_pattern' | 'duplicate_iban'
    existing: ProviderPaymentInfo
    newData: Partial<ProviderPaymentInfo>
  } | null>(null)
  const queryClient = useQueryClient()

  const { data: corrections, isLoading: loadingCorrections } = useQuery({
    queryKey: ['correctionRules'],
    queryFn: () => rulesApi.listCorrections(),
  })

  const { data: matching, isLoading: loadingMatching } = useQuery({
    queryKey: ['matchingRules'],
    queryFn: () => rulesApi.listMatching(),
  })

  const { data: paymentInfo, isLoading: loadingPaymentInfo } = useQuery({
    queryKey: ['paymentInfo'],
    queryFn: () => rulesApi.listPaymentInfo(),
  })

  const handleSaveCorrectionRule = async (data: Partial<CorrectionRule>) => {
    try {
      if (editCorrectionRule) {
        await rulesApi.updateCorrection(editCorrectionRule.id, data)
        setMessage({ type: 'success', text: 'Regel aktualisiert' })
      } else {
        await rulesApi.createCorrection(data as Omit<CorrectionRule, 'id' | 'created_at' | 'updated_at'>)
        setMessage({ type: 'success', text: 'Regel erstellt' })
      }
      queryClient.invalidateQueries({ queryKey: ['correctionRules'] })
      setEditCorrectionRule(null)
      setShowNewCorrectionModal(false)
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Fehler' })
    }
  }

  const handleDeleteCorrectionRule = async (id: string) => {
    if (!confirm('Regel wirklich löschen?')) return
    try {
      await rulesApi.deleteCorrection(id)
      setMessage({ type: 'success', text: 'Regel gelöscht' })
      queryClient.invalidateQueries({ queryKey: ['correctionRules'] })
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Fehler' })
    }
  }

  const handleSaveMatchingRule = async (data: Partial<MatchingRule>) => {
    try {
      if (editMatchingRule) {
        await rulesApi.updateMatching(editMatchingRule.id, data)
        setMessage({ type: 'success', text: 'Regel aktualisiert' })
      } else {
        await rulesApi.createMatching(data as Omit<MatchingRule, 'id' | 'created_at' | 'updated_at'>)
        setMessage({ type: 'success', text: 'Regel erstellt' })
      }
      queryClient.invalidateQueries({ queryKey: ['matchingRules'] })
      setEditMatchingRule(null)
      setShowNewMatchingModal(false)
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Fehler' })
    }
  }

  const handleDeleteMatchingRule = async (id: string) => {
    if (!confirm('Regel wirklich löschen?')) return
    try {
      await rulesApi.deleteMatching(id)
      setMessage({ type: 'success', text: 'Regel gelöscht' })
      queryClient.invalidateQueries({ queryKey: ['matchingRules'] })
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Fehler' })
    }
  }

  const handleSavePaymentInfo = async (data: Partial<ProviderPaymentInfo>) => {
    try {
      if (editPaymentInfo) {
        await rulesApi.updatePaymentInfo(editPaymentInfo.id, data)
        setMessage({ type: 'success', text: 'Bankverbindung aktualisiert' })
      } else {
        await rulesApi.createPaymentInfo(data as Omit<ProviderPaymentInfo, 'id' | 'created_at' | 'updated_at'>)
        setMessage({ type: 'success', text: 'Bankverbindung erstellt' })
      }
      queryClient.invalidateQueries({ queryKey: ['paymentInfo'] })
      setEditPaymentInfo(null)
      setShowNewPaymentInfoModal(false)
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Fehler'
      // Check for 409 conflict with structured detail
      if (errMsg.startsWith('409: ')) {
        try {
          const detail = JSON.parse(errMsg.substring(5))
          if (detail.type && detail.existing) {
            setDuplicateConflict({
              type: detail.type,
              existing: detail.existing,
              newData: data,
            })
            return
          }
        } catch {
          // Not JSON, fall through to error message
        }
      }
      setMessage({ type: 'error', text: errMsg })
    }
  }

  const handleOverwritePaymentInfo = async () => {
    if (!duplicateConflict) return
    try {
      await rulesApi.updatePaymentInfo(duplicateConflict.existing.id, duplicateConflict.newData)
      setMessage({ type: 'success', text: 'Bankverbindung überschrieben' })
      queryClient.invalidateQueries({ queryKey: ['paymentInfo'] })
      setDuplicateConflict(null)
      setEditPaymentInfo(null)
      setShowNewPaymentInfoModal(false)
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Fehler' })
      setDuplicateConflict(null)
    }
  }

  const handleDeletePaymentInfo = async (id: string) => {
    if (!confirm('Bankverbindung wirklich löschen?')) return
    try {
      await rulesApi.deletePaymentInfo(id)
      setMessage({ type: 'success', text: 'Bankverbindung gelöscht' })
      queryClient.invalidateQueries({ queryKey: ['paymentInfo'] })
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Fehler' })
    }
  }

  const fieldNameLabels: Record<string, string> = {
    provider_name: 'Anbieter',
    insured_person: 'Person',
    description: 'Beschreibung',
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Regeln</h1>
        <button
          onClick={() => {
            if (activeTab === 'corrections') setShowNewCorrectionModal(true)
            else if (activeTab === 'matching') setShowNewMatchingModal(true)
            else setShowNewPaymentInfoModal(true)
          }}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
        >
          <Plus className="h-4 w-4" />
          {activeTab === 'bankinfo' ? 'Neue Bankverbindung' : 'Neue Regel'}
        </button>
      </div>

      {/* Status Message */}
      {message && (
        <div className={`p-4 rounded-md ${message.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
          {message.text}
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-4">
          <button
            onClick={() => setActiveTab('corrections')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm ${
              activeTab === 'corrections'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <Settings className="h-4 w-4" />
            Korrekturen ({corrections?.total || 0})
          </button>
          <button
            onClick={() => setActiveTab('matching')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm ${
              activeTab === 'matching'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <Link2 className="h-4 w-4" />
            Matching ({matching?.total || 0})
          </button>
          <button
            onClick={() => setActiveTab('bankinfo')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm ${
              activeTab === 'bankinfo'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <CreditCard className="h-4 w-4" />
            Bankverbindungen ({paymentInfo?.total || 0})
          </button>
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'corrections' && (
        <div className="space-y-4">
          {/* Info Box */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex gap-3">
            <Info className="h-5 w-5 text-blue-500 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-blue-800">
              <p className="font-medium">Korrektur-Regeln</p>
              <p className="mt-1">
                Ändern den Beleg-Text für zukünftige Uploads automatisch.
                Ideal für OCR-Fehler oder falsche Parser-Ergebnisse.
                Der korrigierte Wert wird in der Datenbank gespeichert.
              </p>
            </div>
          </div>

          {/* Table */}
          <div className="bg-white rounded-lg shadow overflow-x-auto">
            {loadingCorrections ? (
              <div className="flex items-center justify-center h-32">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              </div>
            ) : corrections?.rules.length === 0 ? (
              <div className="p-8 text-center text-gray-500">
                Keine Korrektur-Regeln vorhanden
              </div>
            ) : (
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <ColumnHeader
                      label="Feld"
                      tooltip="Welches Datenfeld korrigiert werden soll: Anbieter, Person oder Beschreibung"
                    />
                    <ColumnHeader
                      label="Original"
                      tooltip="Der fehlerhafte Text, wie er vom Parser/OCR erkannt wurde. Muss exakt übereinstimmen."
                    />
                    <ColumnHeader
                      label="Korrektur"
                      tooltip="Der korrekte Text, der stattdessen gespeichert wird. Wird bei zukünftigen Uploads automatisch angewendet."
                    />
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Beschreibung</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Aktiv</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Aktionen</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {corrections?.rules.map((rule) => (
                    <tr key={rule.id} className={`hover:bg-gray-50 ${!rule.active ? 'opacity-50' : ''}`}>
                      <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                        {fieldNameLabels[rule.field_name] || rule.field_name}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 max-w-xs truncate" title={rule.raw_value}>
                        {rule.raw_value}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 max-w-xs truncate" title={rule.corrected_value}>
                        {rule.corrected_value}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500">
                        {rule.description || '-'}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {rule.active ? (
                          <span className="text-green-600">✓</span>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <button
                            onClick={() => setEditCorrectionRule(rule)}
                            className="p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded"
                            title="Bearbeiten"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => handleDeleteCorrectionRule(rule.id)}
                            className="p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded"
                            title="Löschen"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {activeTab === 'matching' && (
        <div className="space-y-4">
          {/* Info Box */}
          <div className="bg-purple-50 border border-purple-200 rounded-lg p-4 flex gap-3">
            <Info className="h-5 w-5 text-purple-500 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-purple-800">
              <p className="font-medium">Matching-Regeln</p>
              <p className="mt-1">
                Helfen bei der Zuordnung von Belegen zu Bankzahlungen, ohne den Beleg zu ändern.
                Für Spezialfälle wie Verhinderungspflege, wo zusätzlich das Leistungsdatum geprüft wird.
              </p>
            </div>
          </div>

          {/* Table */}
          <div className="bg-white rounded-lg shadow overflow-x-auto">
            {loadingMatching ? (
              <div className="flex items-center justify-center h-32">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              </div>
            ) : matching?.rules.length === 0 ? (
              <div className="p-8 text-center text-gray-500">
                Keine Matching-Regeln vorhanden
              </div>
            ) : (
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <ColumnHeader
                      label="Provider"
                      tooltip="Der Anbieter-Name aus dem Beleg. Wird für die Zuordnung zu Bankzahlungen verwendet."
                    />
                    <ColumnHeader
                      label="Bank-Patterns"
                      tooltip="Suchbegriffe die in der Bankbuchung vorkommen müssen. Alle Patterns müssen gefunden werden (UND-Verknüpfung)."
                    />
                    <ColumnHeader
                      label="Typ"
                      tooltip="Standard: Prüft Betrag + Provider. Verhinderungspflege: Prüft zusätzlich das Leistungsdatum im Verwendungszweck."
                    />
                    <ColumnHeader
                      label="Priorität"
                      tooltip="Regeln mit höherer Priorität werden zuerst geprüft. Nützlich wenn mehrere Regeln auf denselben Beleg passen könnten."
                    />
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Beschreibung</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Aktiv</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Aktionen</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {matching?.rules.map((rule) => (
                    <tr key={rule.id} className={`hover:bg-gray-50 ${!rule.active ? 'opacity-50' : ''}`}>
                      <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                        {rule.provider_pattern}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 max-w-xs">
                        <div className="flex flex-wrap gap-1">
                          {rule.bank_patterns.map((p, i) => (
                            <span key={i} className="inline-block px-2 py-0.5 bg-gray-100 rounded text-xs">
                              {p}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          rule.match_type === 'verhinderungspflege'
                            ? 'bg-purple-100 text-purple-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}>
                          {rule.match_type}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center text-sm text-gray-500">
                        {rule.priority}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500">
                        {rule.description || '-'}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {rule.active ? (
                          <span className="text-green-600">✓</span>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <button
                            onClick={() => setEditMatchingRule(rule)}
                            className="p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded"
                            title="Bearbeiten"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => handleDeleteMatchingRule(rule.id)}
                            className="p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded"
                            title="Löschen"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {activeTab === 'bankinfo' && (
        <div className="space-y-4">
          {/* Info Box */}
          <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex gap-3">
            <Info className="h-5 w-5 text-green-500 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-green-800">
              <p className="font-medium">Gespeicherte Bankverbindungen</p>
              <p className="mt-1">
                Werden automatisch beim Erstellen eines SEPA-QR-Codes gespeichert.
                Bei neuen Rechnungen desselben Anbieters werden diese Daten vorausgefüllt.
              </p>
            </div>
          </div>

          {/* Table */}
          <div className="bg-white rounded-lg shadow overflow-x-auto">
            {loadingPaymentInfo ? (
              <div className="flex items-center justify-center h-32">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              </div>
            ) : paymentInfo?.items.length === 0 ? (
              <div className="p-8 text-center text-gray-500">
                Keine Bankverbindungen gespeichert
              </div>
            ) : (
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <ColumnHeader
                      label="Anbieter"
                      tooltip="Matcht wenn dieser Text im Anbieternamen des Belegs enthalten ist (Teilstring, Groß-/Kleinschreibung egal). Wenn übereinstimmend, werden IBAN und Empfänger vorausgefüllt."
                    />
                    <ColumnHeader
                      label="Empfänger"
                      tooltip="Name des Zahlungsempfängers für SEPA-Überweisungen. Wird im QR-Code und beim PDF-Export verwendet."
                    />
                    <ColumnHeader
                      label="IBAN"
                      tooltip="Internationale Bankkontonummer des Empfängers. Wird automatisch beim Speichern eines QR-Codes gespeichert."
                    />
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Erstellt</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Aktiv</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Aktionen</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {paymentInfo?.items.map((info) => (
                    <tr key={info.id} className={`hover:bg-gray-50 ${!info.active ? 'opacity-50' : ''}`}>
                      <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 font-medium">
                        {info.provider_pattern}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500">
                        {info.payment_recipient || '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 font-mono">
                        {info.payment_iban
                          ? info.payment_iban.replace(/(.{4})/g, '$1 ').trim()
                          : '-'}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-400">
                        {info.created_at ? formatDate(info.created_at.split('T')[0]) : '-'}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {info.active ? (
                          <span className="text-green-600">✓</span>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <button
                            onClick={() => setEditPaymentInfo(info)}
                            className="p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded"
                            title="Bearbeiten"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => handleDeletePaymentInfo(info.id)}
                            className="p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded"
                            title="Löschen"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* Modals */}
      {(showNewCorrectionModal || editCorrectionRule) && (
        <CorrectionRuleModal
          rule={editCorrectionRule}
          onClose={() => {
            setShowNewCorrectionModal(false)
            setEditCorrectionRule(null)
          }}
          onSave={handleSaveCorrectionRule}
        />
      )}

      {(showNewMatchingModal || editMatchingRule) && (
        <MatchingRuleModal
          rule={editMatchingRule}
          onClose={() => {
            setShowNewMatchingModal(false)
            setEditMatchingRule(null)
          }}
          onSave={handleSaveMatchingRule}
        />
      )}

      {(showNewPaymentInfoModal || editPaymentInfo) && (
        <PaymentInfoModal
          info={editPaymentInfo}
          onClose={() => {
            setShowNewPaymentInfoModal(false)
            setEditPaymentInfo(null)
          }}
          onSave={handleSavePaymentInfo}
        />
      )}

      {/* Duplicate Conflict Dialog */}
      {duplicateConflict && (
        <div className="fixed inset-0 z-[60] overflow-y-auto">
          <div className="flex min-h-screen items-center justify-center p-4">
            <div className="fixed inset-0 bg-black/50" onClick={() => setDuplicateConflict(null)} />
            <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full">
              <div className="flex items-center justify-between px-6 py-4 border-b bg-orange-50 rounded-t-lg">
                <h2 className="text-lg font-semibold text-orange-800">
                  Bankverbindung existiert bereits
                </h2>
                <button onClick={() => setDuplicateConflict(null)} className="text-orange-600 hover:text-orange-800">
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="px-6 py-4 space-y-4">
                <p className="text-sm text-gray-700">
                  {duplicateConflict.type === 'duplicate_iban'
                    ? 'Diese IBAN ist bereits für einen anderen Anbieter gespeichert:'
                    : 'Für diesen Anbieter existiert bereits eine Bankverbindung:'}
                </p>

                <div className="bg-gray-50 rounded-lg p-3 space-y-1 text-sm">
                  <div>
                    <span className="text-gray-500">Anbieter:</span>{' '}
                    <span className="font-medium">{duplicateConflict.existing.provider_pattern}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Empfänger:</span>{' '}
                    <span className="font-medium">{duplicateConflict.existing.payment_recipient || '-'}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">IBAN:</span>{' '}
                    <span className="font-medium font-mono">
                      {duplicateConflict.existing.payment_iban
                        ? duplicateConflict.existing.payment_iban.replace(/(.{4})/g, '$1 ').trim()
                        : '-'}
                    </span>
                  </div>
                </div>

                <p className="text-sm text-gray-600">
                  Möchtest du die bestehende Regel überschreiben?
                </p>
              </div>

              <div className="flex items-center justify-end gap-2 px-6 py-4 border-t bg-gray-50 rounded-b-lg">
                <button
                  onClick={() => setDuplicateConflict(null)}
                  className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md"
                >
                  Abbrechen
                </button>
                <button
                  onClick={handleOverwritePaymentInfo}
                  className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700"
                >
                  Überschreiben
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
