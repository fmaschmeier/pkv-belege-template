import { supabase } from './supabase'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function getAuthHeaders(): Promise<HeadersInit> {
  const { data: { session } } = await supabase.auth.getSession()

  if (!session?.access_token) {
    throw new AuthError('Nicht eingeloggt')
  }

  return {
    'Authorization': `Bearer ${session.access_token}`,
    'Content-Type': 'application/json',
  }
}

// Custom error class for auth errors
export class AuthError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AuthError'
  }
}

async function handleAuthError() {
  // Sign out and redirect to login
  await supabase.auth.signOut()
  window.location.href = '/login'
}

async function fetchApi<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  let headers: HeadersInit
  try {
    headers = await getAuthHeaders()
  } catch (e) {
    if (e instanceof AuthError) {
      await handleAuthError()
    }
    throw e
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      ...headers,
      ...options.headers,
    },
  })

  // Handle auth errors (401 Unauthorized, 403 Forbidden)
  if (response.status === 401 || response.status === 403) {
    await handleAuthError()
    throw new AuthError('Session abgelaufen')
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unbekannter Fehler' }))
    // Handle 409 conflict with structured detail (e.g., linked_receipt info)
    if (response.status === 409 && typeof error.detail === 'object') {
      throw new Error(`409: ${JSON.stringify(error.detail)}`)
    }
    const message = typeof error.detail === 'string' ? error.detail : `HTTP ${response.status}`
    throw new Error(message)
  }

  return response.json()
}

// Settlements API
export const settlementsApi = {
  list: (params?: { limit?: number; offset?: number; year?: number; person?: string }) => {
    const searchParams = new URLSearchParams()
    if (params?.limit) searchParams.set('limit', params.limit.toString())
    if (params?.offset) searchParams.set('offset', params.offset.toString())
    if (params?.year) searchParams.set('year', params.year.toString())
    if (params?.person) searchParams.set('person', params.person)

    return fetchApi<SettlementListResponse>(`/settlements?${searchParams}`)
  },

  get: (id: string) => fetchApi<Settlement>(`/settlements/${id}`),

  stats: (year?: number) => {
    const params = year ? `?year=${year}` : ''
    return fetchApi<SettlementStats>(`/settlements/stats/summary${params}`)
  },

  upload: async (file: File) => {
    const headers = await getAuthHeaders()
    delete (headers as Record<string, string>)['Content-Type']

    const formData = new FormData()
    formData.append('file', file)

    const response = await fetch(`${API_URL}/settlements/upload`, {
      method: 'POST',
      headers,
      body: formData,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload fehlgeschlagen' }))
      throw new Error(error.detail)
    }

    return response.json()
  },

  uploadPdf: async (settlementId: string, file: File) => {
    const headers = await getAuthHeaders()
    delete (headers as Record<string, string>)['Content-Type']

    const formData = new FormData()
    formData.append('file', file)

    const response = await fetch(`${API_URL}/settlements/${settlementId}/upload-pdf`, {
      method: 'POST',
      headers,
      body: formData,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload fehlgeschlagen' }))
      throw new Error(error.detail)
    }

    return response.json() as Promise<{ success: boolean; storage_path: string; message: string }>
  },

  getPdfUrl: (settlementId: string) =>
    fetchApi<{ signed_url: string; expires_in: number; filename: string | null }>(
      `/settlements/${settlementId}/pdf-url`
    ),

  updateItem: (itemId: string, data: Partial<SettlementItem>) =>
    fetchApi<SettlementItem>(`/settlements/items/${itemId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
}

// Items API
export const itemsApi = {
  list: (params?: {
    limit?: number
    offset?: number
    person?: string
    date_from?: string
    date_to?: string
    year?: number
    month?: number
  }) => {
    const searchParams = new URLSearchParams()
    if (params?.limit) searchParams.set('limit', params.limit.toString())
    if (params?.offset) searchParams.set('offset', params.offset.toString())
    if (params?.person) searchParams.set('person', params.person)
    if (params?.date_from) searchParams.set('date_from', params.date_from)
    if (params?.date_to) searchParams.set('date_to', params.date_to)
    if (params?.year) searchParams.set('year', params.year.toString())
    if (params?.month) searchParams.set('month', params.month.toString())

    return fetchApi<ItemListResponse>(`/items?${searchParams}`)
  },

  unlinked: (params?: { limit?: number; offset?: number }) => {
    const searchParams = new URLSearchParams()
    if (params?.limit) searchParams.set('limit', params.limit.toString())
    if (params?.offset) searchParams.set('offset', params.offset.toString())
    return fetchApi<ItemListResponse>(`/items/unlinked?${searchParams}`)
  },

  search: (params: { amount: number; person?: string; treatment_date?: string; submission_date?: string }) => {
    const searchParams = new URLSearchParams()
    searchParams.set('amount', params.amount.toString())
    if (params.person) searchParams.set('person', params.person)
    if (params.treatment_date) searchParams.set('treatment_date', params.treatment_date)
    if (params.submission_date) searchParams.set('submission_date', params.submission_date)
    return fetchApi<ItemSearchResponse>(`/items/search?${searchParams}`)
  },
}

// Bank API
export const bankApi = {
  transactions: (params?: {
    limit?: number
    offset?: number
    universa_only?: boolean
    unmatched_only?: boolean
    year?: number
    month?: number
  }) => {
    const searchParams = new URLSearchParams()
    if (params?.limit) searchParams.set('limit', params.limit.toString())
    if (params?.offset) searchParams.set('offset', params.offset.toString())
    if (params?.universa_only) searchParams.set('universa_only', 'true')
    if (params?.unmatched_only) searchParams.set('unmatched_only', 'true')
    if (params?.year) searchParams.set('year', params.year.toString())
    if (params?.month) searchParams.set('month', params.month.toString())

    return fetchApi<BankTransactionListResponse>(`/bank/transactions?${searchParams}`)
  },

  stats: (year?: number) => {
    const params = year ? `?year=${year}` : ''
    return fetchApi<BankStats>(`/bank/stats/summary${params}`)
  },

  getTransaction: (transactionId: string) =>
    fetchApi<BankTransaction>(`/bank/transactions/${transactionId}`),

  universaMatches: () => fetchApi<UniversaMatchesResponse>('/bank/universa-matches'),

  updateLinks: () => fetchApi<{ success: boolean; updated: number }>('/bank/update-links', { method: 'POST' }),

  importCsv: async (file: File) => {
    const headers = await getAuthHeaders()
    delete (headers as Record<string, string>)['Content-Type']

    const formData = new FormData()
    formData.append('file', file)

    const response = await fetch(`${API_URL}/bank/import`, {
      method: 'POST',
      headers,
      body: formData,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Import fehlgeschlagen' }))
      throw new Error(error.detail)
    }

    return response.json()
  },
}

// Types
export interface Settlement {
  id: string
  settlement_number: string
  settlement_date: string
  insurance_number: string
  total_invoiced: number | null
  total_reimbursed: number | null
  pdf_filename: string | null
  pdf_url: string | null
  raw_text: string | null
  settlement_items: SettlementItem[]
}

export interface SettlementItem {
  id: string
  settlement_id: string
  receipt_number: string
  tariff: string | null
  insured_person: string | null
  description: string | null
  treatment_period: string | null
  invoice_amount: number | null
  reimbursed_amount: number | null
  notes: string | null
  payment_status: string
  payment_note: string | null
}

export interface SettlementListResponse {
  settlements: Settlement[]
  total: number
}

export interface SettlementStats {
  settlements_count: number
  items_count: number
  total_reimbursed: number
  year: string | number
}

export interface LinkedReceiptInfo {
  id: string
  provider_name: string | null
  invoice_amount: number | null
  status: string
}

export interface BankTransaction {
  id: string
  booking_date: string
  value_date: string
  transaction_type: string | null
  description: string
  amount: number
  currency: string
  category: string | null
  is_universa_payment: boolean
  settlement_id: string | null
  linked_receipt: LinkedReceiptInfo | null
}

export interface BankTransactionListResponse {
  transactions: BankTransaction[]
  total: number
  total_amount: number
}

export interface BankStats {
  total_transactions: number
  total_expenses: number
  total_expenses_amount: number
  universa_payments: number
  universa_matched: number
  universa_unmatched: number
  universa_total_amount: number
  year: string | number
}

export interface UniversaMatchesResponse {
  total: number
  matched: number
  unmatched: number
  payments: {
    id: string
    booking_date: string
    amount: number
    settlement_id: string | null
    settlement_number: string | null
    matched: boolean
  }[]
}

export interface ItemWithSettlement {
  id: string
  settlement_id: string
  settlement_number: string
  settlement_date: string
  receipt_number: string
  tariff: string | null
  insured_person: string | null
  description: string | null
  treatment_period: string | null
  invoice_amount: number | null
  reimbursed_amount: number | null
  notes: string | null
  payment_status: string
  payment_note: string | null
}

export interface ItemListResponse {
  items: ItemWithSettlement[]
  total: number
  total_reimbursed: number
  total_invoiced: number
}

export interface ItemMatch {
  id: string
  receipt_number: string
  settlement_number: string
  settlement_date: string
  insured_person: string | null
  description: string | null
  treatment_period: string | null
  invoice_amount: number | null
  reimbursed_amount: number | null
  match_score: number
}

export interface ItemSearchResponse {
  matches: ItemMatch[]
  total: number
}

// Receipts API
export const receiptsApi = {
  list: (params?: {
    limit?: number
    offset?: number
    status?: string
    person?: string
    receipt_type?: string
    overdue_only?: boolean
  }) => {
    const searchParams = new URLSearchParams()
    if (params?.limit) searchParams.set('limit', params.limit.toString())
    if (params?.offset) searchParams.set('offset', params.offset.toString())
    if (params?.status) searchParams.set('status', params.status)
    if (params?.person) searchParams.set('person', params.person)
    if (params?.receipt_type) searchParams.set('receipt_type', params.receipt_type)
    if (params?.overdue_only) searchParams.set('overdue_only', 'true')

    return fetchApi<ReceiptListResponse>(`/receipts?${searchParams}`)
  },

  get: (id: string) => fetchApi<Receipt>(`/receipts/${id}`),

  stats: () => fetchApi<ReceiptStats>('/receipts/stats'),

  upload: async (file: File) => {
    const headers = await getAuthHeaders()
    delete (headers as Record<string, string>)['Content-Type']

    const formData = new FormData()
    formData.append('file', file)

    const response = await fetch(`${API_URL}/receipts/upload`, {
      method: 'POST',
      headers,
      body: formData,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload fehlgeschlagen' }))
      throw new Error(error.detail)
    }

    return response.json() as Promise<ReceiptUploadResponse>
  },

  update: (id: string, data: Partial<Receipt>) =>
    fetchApi<Receipt>(`/receipts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    fetchApi<{ success: boolean }>(`/receipts/${id}`, { method: 'DELETE' }),

  matchSettlements: () =>
    fetchApi<{ success: boolean; matched: number }>('/receipts/match-settlements', { method: 'POST' }),

  matchPayments: () =>
    fetchApi<{ success: boolean; matched: number; checked: number }>('/receipts/match-payments', { method: 'POST' }),

  suggestPayments: (receiptId: string) =>
    fetchApi<PaymentSuggestions>(`/receipts/${receiptId}/suggest-payments`),

  uploadPdf: async (receiptId: string, file: File) => {
    const headers = await getAuthHeaders()
    delete (headers as Record<string, string>)['Content-Type']

    const formData = new FormData()
    formData.append('file', file)

    const response = await fetch(`${API_URL}/receipts/${receiptId}/upload-pdf`, {
      method: 'POST',
      headers,
      body: formData,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload fehlgeschlagen' }))
      throw new Error(error.detail)
    }

    return response.json() as Promise<{ success: boolean; storage_path: string; message: string }>
  },

  getPdfUrl: (receiptId: string) =>
    fetchApi<{ signed_url: string; expires_in: number; filename: string | null }>(
      `/receipts/${receiptId}/pdf-url`
    ),

  deletePdf: (receiptId: string) =>
    fetchApi<{ success: boolean; message: string }>(
      `/receipts/${receiptId}/pdf`,
      { method: 'DELETE' }
    ),

  reparse: (receiptId: string) =>
    fetchApi<{ success: boolean; receipt_id: string; parsed_params: Record<string, unknown>; message: string; receipt?: Receipt }>(
      `/receipts/${receiptId}/reparse`,
      { method: 'POST' }
    ),

  getPaymentDefaults: (receiptId: string) =>
    fetchApi<PaymentDefaults>(`/receipts/${receiptId}/payment-defaults`),

  generatePaymentQR: (receiptId: string, data: PaymentQRRequest) =>
    fetchApi<PaymentQRResponse>(`/receipts/${receiptId}/payment-qr`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
}

export interface Receipt {
  id: string
  submission_date: string
  pdf_filename: string
  pdf_hash: string
  filename_person: string | null
  filename_provider: string | null
  receipt_type: string | null
  provider_name: string | null
  provider_address: string | null
  invoice_number: string | null
  invoice_date: string | null
  invoice_amount: number | null
  insured_person: string | null
  insured_birthdate: string | null
  description: string | null
  treatment_period: string | null
  due_date: string | null
  due_date_source: string | null
  status: string  // submitted | reimbursed | rejected

  // === PKV-ERSTATTUNG (Beziehung zur Krankenversicherung) ===
  settlement_item_id: string | null  // Verknüpfung mit Erstattungsposition
  reimbursed_amount: number | null   // Erstatteter Betrag von PKV
  reimbursed_date: string | null     // Datum der PKV-Erstattung
  rejection_reason: string | null    // Ablehnungsgrund (wenn rejected)
  settlement_number: string | null   // z.B. "R/26/117" (aus JOIN)
  receipt_number: string | null      // z.B. "B/26/1201" (aus JOIN)

  // === ZAHLUNG AN LEISTUNGSERBRINGER (Arzt, Apotheke, etc.) ===
  payment_transaction_id: string | null  // Verknüpfung mit Banktransaktion
  paid_date: string | null               // Zahlungsdatum an Leistungserbringer
  paid_amount: number | null             // Bezahlter Betrag (aus Transaktion)
  payment_description: string | null     // Buchungstext (aus Transaktion, max 50 Zeichen)
  // Zahlungsdaten für QR-Code Generierung
  payment_recipient: string | null       // Überweisungsempfänger
  payment_iban: string | null            // IBAN des Empfängers
  payment_reference: string | null       // Verwendungszweck

  // === PDF & PARSING ===
  pdf_url: string | null
  raw_text: string | null
  parsed_params: Record<string, unknown> | null  // Original geparste Daten von Claude Vision
}

export interface ReceiptListResponse {
  receipts: Receipt[]
  total: number  // Gesamtanzahl aller Belege

  // === PKV-ERSTATTUNG ===
  pending_count: number                  // Belege mit status='submitted' (noch nicht erstattet)
  reimbursement_overdue_count: number    // Erstattung überfällig (>30 Tage seit Einreichung)
  total_amount: number                   // Summe der offenen Belege (nur pending)

  // === ZAHLUNG AN LEISTUNGSERBRINGER ===
  unpaid_count: number                   // Nicht bezahlt (unabhängig von Erstattungsstatus)
  overdue_count: number                  // Zahlung überfällig (due_date überschritten, nicht bezahlt)

  // === LIQUIDITÄT ===
  // Minus Summe aller Belege, die bezahlt, aber noch nicht erstattet sind (Rezepte gelten als bezahlt).
  // Negativ = so viel Geld ist aktuell vorgestreckt ("draußen"); 0 = nichts vorgestreckt
  liqui_saldo: number
}

export interface ReceiptUploadResponse {
  success: boolean
  receipt_id: string
  receipt_type: string
  invoice_amount: number | null
  due_date: string | null
  message: string
}

export interface ReceiptStats {
  total_count: number
  submitted_count: number
  reimbursed_count: number
  rejected_count: number
  total_submitted_amount: number
  total_reimbursed_amount: number
  overdue_count: number
  due_soon_count: number
}

export interface SuggestedTransactionLinkedInfo {
  receipt_id: string
  provider_name: string | null
  invoice_amount: number | null
  invoice_date: string | null
}

export interface SuggestedTransaction extends BankTransaction {
  treatment_date: string | null
  match_reason: string
  linked_to_receipt: SuggestedTransactionLinkedInfo | null
}

export interface PaymentSuggestions {
  receipt_id: string
  matching: SuggestedTransaction[]
  same_amount: SuggestedTransaction[]
}

// === Payment QR Code ===

export interface PaymentDefaults {
  receipt_id: string
  recipient: string
  iban: string
  reference: string
  amount: number
  iban_valid: boolean
  provider_name: string | null
  invoice_number: string | null
  invoice_date: string | null
}

export interface PaymentQRRequest {
  recipient: string
  iban: string
  amount: number
  reference: string
}

export interface PaymentQRResponse {
  success: boolean
  qr_data: string | null
  recipient: string
  iban: string
  amount: number
  reference: string
  iban_valid: boolean
  error: string | null
}

// === Rules API ===

// Correction Rules - für Parser-Korrekturen
export interface CorrectionRule {
  id: string
  field_name: string
  raw_value: string
  corrected_value: string
  active: boolean
  description: string | null
  created_at: string
  updated_at: string
}

export interface CorrectionRuleListResponse {
  rules: CorrectionRule[]
  total: number
}

// Matching Rules - für Beleg ↔ Bank Zuordnung (Spezialfälle)
export interface MatchingRule {
  id: string
  provider_pattern: string
  bank_patterns: string[]
  match_type: string
  priority: number
  active: boolean
  description: string | null
  created_at: string
  updated_at: string
}

export interface MatchingRuleListResponse {
  rules: MatchingRule[]
  total: number
}

// Provider Payment Info - Gespeicherte Bankverbindungen
export interface ProviderPaymentInfo {
  id: string
  provider_pattern: string
  payment_recipient: string | null
  payment_iban: string | null
  active: boolean
  created_at: string
  updated_at: string
}

export interface ProviderPaymentInfoListResponse {
  items: ProviderPaymentInfo[]
  total: number
}

export const rulesApi = {
  // Correction Rules
  listCorrections: (activeOnly = false) => {
    const params = activeOnly ? '?active_only=true' : ''
    return fetchApi<CorrectionRuleListResponse>(`/rules/corrections${params}`)
  },

  getCorrection: (id: string) =>
    fetchApi<CorrectionRule>(`/rules/corrections/${id}`),

  createCorrection: (data: Omit<CorrectionRule, 'id' | 'created_at' | 'updated_at'>) =>
    fetchApi<CorrectionRule>('/rules/corrections', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateCorrection: (id: string, data: Partial<CorrectionRule>) =>
    fetchApi<CorrectionRule>(`/rules/corrections/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteCorrection: (id: string) =>
    fetchApi<{ success: boolean }>(`/rules/corrections/${id}`, { method: 'DELETE' }),

  // Matching Rules
  listMatching: (activeOnly = false) => {
    const params = activeOnly ? '?active_only=true' : ''
    return fetchApi<MatchingRuleListResponse>(`/rules/matching${params}`)
  },

  getMatching: (id: string) =>
    fetchApi<MatchingRule>(`/rules/matching/${id}`),

  createMatching: (data: Omit<MatchingRule, 'id' | 'created_at' | 'updated_at'>) =>
    fetchApi<MatchingRule>('/rules/matching', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateMatching: (id: string, data: Partial<MatchingRule>) =>
    fetchApi<MatchingRule>(`/rules/matching/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteMatching: (id: string) =>
    fetchApi<{ success: boolean }>(`/rules/matching/${id}`, { method: 'DELETE' }),

  // Provider Payment Info (Bankverbindungen)
  listPaymentInfo: (activeOnly = false) => {
    const params = activeOnly ? '?active_only=true' : ''
    return fetchApi<ProviderPaymentInfoListResponse>(`/rules/payment-info${params}`)
  },

  getPaymentInfo: (id: string) =>
    fetchApi<ProviderPaymentInfo>(`/rules/payment-info/${id}`),

  createPaymentInfo: (data: Omit<ProviderPaymentInfo, 'id' | 'created_at' | 'updated_at'>) =>
    fetchApi<ProviderPaymentInfo>('/rules/payment-info', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updatePaymentInfo: (id: string, data: Partial<ProviderPaymentInfo>) =>
    fetchApi<ProviderPaymentInfo>(`/rules/payment-info/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deletePaymentInfo: (id: string) =>
    fetchApi<{ success: boolean }>(`/rules/payment-info/${id}`, { method: 'DELETE' }),
}
