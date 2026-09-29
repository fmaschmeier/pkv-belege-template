import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { receiptsApi } from '../lib/api'
import type { Receipt } from '../lib/api'
import { formatDate, formatCurrency } from '../lib/utils'
import { Mail, Copy, Check, Download, AlertTriangle, Clock, FileText } from 'lucide-react'

// Configuration from environment variables
const CONFIG = {
  insuranceNumber: import.meta.env.VITE_INSURANCE_NUMBER || '',
  recipientEmail: import.meta.env.VITE_RECIPIENT_EMAIL || '',
  ccEmail: import.meta.env.VITE_CC_EMAIL || '',
  senderName: import.meta.env.VITE_SENDER_NAME || '',
  senderEmail: import.meta.env.VITE_SENDER_EMAIL || '',
  senderMobile: import.meta.env.VITE_SENDER_MOBILE || '',
}

// Helper to calculate days since submission
function daysSinceSubmission(submissionDate: string): number {
  const submitted = new Date(submissionDate)
  const today = new Date()
  const diffTime = today.getTime() - submitted.getTime()
  return Math.floor(diffTime / (1000 * 60 * 60 * 24))
}

// Helper to calculate deadline date (30 days from submission)
function getDeadlineDate(submissionDate: string): Date {
  const submitted = new Date(submissionDate)
  return new Date(submitted.getTime() + 30 * 24 * 60 * 60 * 1000)
}

// Helper to format date in German style
function formatGermanDate(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

// Group receipts by submission date for combined emails
interface ReceiptGroup {
  submissionDate: string
  receipts: Receipt[]
  totalAmount: number
  daysOverdue: number
  deadlineDate: Date
}

function groupReceiptsBySubmission(receipts: Receipt[]): ReceiptGroup[] {
  const groups: Record<string, Receipt[]> = {}

  receipts.forEach(r => {
    const key = r.submission_date
    if (!groups[key]) groups[key] = []
    groups[key].push(r)
  })

  return Object.entries(groups)
    .map(([submissionDate, receipts]) => ({
      submissionDate,
      receipts,
      totalAmount: receipts.reduce((sum, r) => sum + (r.invoice_amount || 0), 0),
      daysOverdue: daysSinceSubmission(submissionDate) - 30,
      deadlineDate: getDeadlineDate(submissionDate),
    }))
    .sort((a, b) => a.daysOverdue - b.daysOverdue) // Most overdue first
}

// Generate subject line
function generateSubject(group: ReceiptGroup, isOverdue: boolean): string {
  const submissionDateStr = formatGermanDate(group.submissionDate)

  const deadlineDateStr = formatGermanDate(group.deadlineDate)

  if (isOverdue) {
    return `Vertragswidrige Verzögerung der Erstattung – Fristsetzung gemäß § 14 VVG (Belege vom ${submissionDateStr} / Vers.-Nr. ${CONFIG.insuranceNumber})`
  } else {
    return `Ausstehende Erstattung – Frist endet am ${deadlineDateStr} (Belege vom ${submissionDateStr} / Vers.-Nr. ${CONFIG.insuranceNumber})`
  }
}

// Generate email body for overdue receipts
function generateOverdueBody(group: ReceiptGroup): string {
  const submissionDateStr = formatGermanDate(group.submissionDate)
  const deadlineDateStr = formatGermanDate(group.deadlineDate)
  const daysOverdue = group.daysOverdue

  // Build receipt list: Behandler, Rechnungsdatum, Patient, Betrag
  const receiptList = group.receipts
    .map(r => {
      const provider = r.provider_name || 'Unbekannt'
      const invoiceDate = r.invoice_date ? formatGermanDate(r.invoice_date) : '-'
      const patient = r.insured_person || '-'
      const amount = formatCurrency(r.invoice_amount || 0)
      return `  • ${provider}, ${invoiceDate}, ${patient}: ${amount}`
    })
    .join('\n')

  // Calculate a reasonable deadline for advance payment (e.g., 7 days from now)
  const advanceDeadline = new Date()
  advanceDeadline.setDate(advanceDeadline.getDate() + 7)
  const advanceDeadlineStr = formatGermanDate(advanceDeadline)

  return `Sehr geehrte Damen und Herren,

die am ${submissionDateStr} eingereichten Belege (Versicherungsnummer ${CONFIG.insuranceNumber}) wurden bislang nicht erstattet. Durch die ausbleibende Zahlung besteht mittlerweile Verzug gegenüber den Leistungserbringern, mit entsprechenden Auswirkungen auf den weiteren Ablauf.

Eingereichte Belege:
${receiptList}
Gesamt: ${formatCurrency(group.totalAmount)}

Nach § 14 Abs. 1 VVG werden Geldleistungen fällig, sobald die zur Feststellung des Versicherungsfalles und des Leistungsumfangs notwendigen Erhebungen beendet sind. Die Unterlagen liegen Ihnen seit dem ${submissionDateStr} vor; die Monatsfrist des § 14 Abs. 2 VVG ist am ${deadlineDateStr} abgelaufen, also vor ${daysOverdue} Tagen. Eine besondere Prüfungskomplexität ist im vorliegenden Fall nicht ersichtlich.

Ich verlange daher gemäß § 14 Abs. 2 VVG eine Abschlagszahlung in Höhe des Betrags, den Sie voraussichtlich mindestens zu zahlen haben – spätestens bis zum ${advanceDeadlineStr}.

Ich ersuche Sie nunmehr ausdrücklich, sowohl aktuell als auch zukünftig eine zügige Bearbeitung und Auszahlung sicherzustellen.

Mit freundlichen Grüßen

${CONFIG.senderName}

_____________________________

${CONFIG.senderName}

Mobil: ${CONFIG.senderMobile}
${CONFIG.senderEmail}`
}

// Generate email body for soon-due receipts (reminder before deadline)
function generateSoonDueBody(group: ReceiptGroup): string {
  const submissionDateStr = formatGermanDate(group.submissionDate)
  const deadlineDateStr = formatGermanDate(group.deadlineDate)
  const daysUntilDeadline = -group.daysOverdue // Positive number for days remaining

  // Build receipt list: Behandler, Rechnungsdatum, Patient, Betrag
  const receiptList = group.receipts
    .map(r => {
      const provider = r.provider_name || 'Unbekannt'
      const invoiceDate = r.invoice_date ? formatGermanDate(r.invoice_date) : '-'
      const patient = r.insured_person || '-'
      const amount = formatCurrency(r.invoice_amount || 0)
      return `  • ${provider}, ${invoiceDate}, ${patient}: ${amount}`
    })
    .join('\n')

  return `Sehr geehrte Damen und Herren,

die am ${submissionDateStr} eingereichten Belege (Versicherungsnummer ${CONFIG.insuranceNumber}) wurden bislang nicht erstattet.

Eingereichte Belege:
${receiptList}
Gesamt: ${formatCurrency(group.totalAmount)}

Ich weise darauf hin, dass Geldleistungen nach § 14 Abs. 1 VVG fällig werden, sobald die notwendigen Erhebungen beendet sind. Ist die Prüfung einen Monat nach Einreichung nicht abgeschlossen, kann ich nach § 14 Abs. 2 VVG Abschlagszahlungen verlangen; diese Frist endet in ${daysUntilDeadline} Tagen am ${deadlineDateStr}. Im vorliegenden Fall ist eine außerordentliche Prüfnotwendigkeit nicht ersichtlich.

Für den Fall, dass die Prüfung bis dahin nicht abgeschlossen ist, verlange ich bereits jetzt gemäß § 14 Abs. 2 VVG eine Abschlagszahlung in Höhe des Betrags, den Sie voraussichtlich mindestens zu zahlen haben.

Ich bitte um zeitnahe Bearbeitung und Auszahlung.

Mit freundlichen Grüßen

${CONFIG.senderName}

_____________________________

${CONFIG.senderName}

Mobil: ${CONFIG.senderMobile}
${CONFIG.senderEmail}`
}

// Generate .eml file content
function generateEmlContent(subject: string, body: string): string {
  const date = new Date().toUTCString()
  const boundary = `----=_Part_${Date.now()}`

  // Encode subject for non-ASCII characters
  const encodedSubject = `=?UTF-8?B?${btoa(unescape(encodeURIComponent(subject)))}?=`

  // Convert body to quoted-printable (simplified - just handle basic German chars)
  const encodedBody = body
    .replace(/ä/g, '=C3=A4')
    .replace(/ö/g, '=C3=B6')
    .replace(/ü/g, '=C3=BC')
    .replace(/Ä/g, '=C3=84')
    .replace(/Ö/g, '=C3=96')
    .replace(/Ü/g, '=C3=9C')
    .replace(/ß/g, '=C3=9F')
    .replace(/€/g, '=E2=82=AC')
    .replace(/–/g, '=E2=80=93')
    .replace(/§/g, '=C2=A7')
    .split('\n')
    .map(line => line.length > 76 ? line.match(/.{1,75}/g)?.join('=\n') || line : line)
    .join('\n')

  return `From: ${CONFIG.senderName} <${CONFIG.senderEmail}>
To: ${CONFIG.recipientEmail}
Cc: ${CONFIG.ccEmail}
Subject: ${encodedSubject}
Date: ${date}
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="${boundary}"

--${boundary}
Content-Type: text/plain; charset=utf-8
Content-Transfer-Encoding: quoted-printable

${encodedBody}

--${boundary}--
`
}

// Download .eml file
function downloadEml(subject: string, body: string, filename: string) {
  const emlContent = generateEmlContent(subject, body)
  const blob = new Blob([emlContent], { type: 'message/rfc822' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// Email Card Component
function EmailCard({
  group,
  isOverdue
}: {
  group: ReceiptGroup
  isOverdue: boolean
}) {
  const [copiedSubject, setCopiedSubject] = useState(false)
  const [copiedBody, setCopiedBody] = useState(false)
  const [copiedAll, setCopiedAll] = useState(false)

  const subject = generateSubject(group, isOverdue)
  const body = isOverdue ? generateOverdueBody(group) : generateSoonDueBody(group)

  const copyToClipboard = async (text: string, type: 'subject' | 'body' | 'all') => {
    await navigator.clipboard.writeText(text)
    if (type === 'subject') {
      setCopiedSubject(true)
      setTimeout(() => setCopiedSubject(false), 2000)
    } else if (type === 'body') {
      setCopiedBody(true)
      setTimeout(() => setCopiedBody(false), 2000)
    } else {
      setCopiedAll(true)
      setTimeout(() => setCopiedAll(false), 2000)
    }
  }

  const handleDownloadEml = () => {
    const dateStr = group.submissionDate.replace(/-/g, '')
    const filename = `mahnung_${dateStr}_${isOverdue ? 'ueberfaellig' : 'bald_faellig'}.eml`
    downloadEml(subject, body, filename)
  }

  return (
    <div className={`bg-white rounded-lg shadow-sm border ${isOverdue ? 'border-red-200' : 'border-yellow-200'}`}>
      {/* Header */}
      <div className={`px-4 py-3 border-b ${isOverdue ? 'bg-red-50 border-red-200' : 'bg-yellow-50 border-yellow-200'}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {isOverdue ? (
              <AlertTriangle className="h-5 w-5 text-red-600" />
            ) : (
              <Clock className="h-5 w-5 text-yellow-600" />
            )}
            <span className={`font-medium ${isOverdue ? 'text-red-800' : 'text-yellow-800'}`}>
              Einreichung vom {formatDate(group.submissionDate)}
            </span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            {isOverdue ? (
              <span className="text-red-600 font-medium">
                {group.daysOverdue} Tage überfällig
              </span>
            ) : (
              <span className="text-yellow-600 font-medium">
                Frist in {-group.daysOverdue} Tagen
              </span>
            )}
            <span className="text-gray-500">•</span>
            <span className="text-gray-600">
              {group.receipts.length} Beleg{group.receipts.length > 1 ? 'e' : ''} • {formatCurrency(group.totalAmount)}
            </span>
          </div>
        </div>
      </div>

      {/* Receipt List */}
      <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
        <div className="text-sm text-gray-600">
          {group.receipts.map((r) => (
            <div key={r.id} className="flex justify-between py-0.5">
              <span>{r.provider_name || 'Unbekannt'}</span>
              <span>{formatCurrency(r.invoice_amount || 0)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Email Content */}
      <div className="p-4 space-y-4">
        {/* Email Addresses */}
        <div className="flex gap-4 text-sm">
          <div>
            <span className="text-gray-500">An:</span>{' '}
            <span className="font-mono text-gray-700">{CONFIG.recipientEmail}</span>
          </div>
          <div>
            <span className="text-gray-500">CC:</span>{' '}
            <span className="font-mono text-gray-700">{CONFIG.ccEmail}</span>
          </div>
        </div>

        {/* Subject */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-sm font-medium text-gray-700">Betreff</label>
            <button
              onClick={() => copyToClipboard(subject, 'subject')}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
            >
              {copiedSubject ? <Check className="h-3 w-3 text-green-600" /> : <Copy className="h-3 w-3" />}
              {copiedSubject ? 'Kopiert!' : 'Kopieren'}
            </button>
          </div>
          <div className="p-2 bg-gray-50 rounded border text-sm font-mono break-words">
            {subject}
          </div>
        </div>

        {/* Body */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-sm font-medium text-gray-700">Text</label>
            <button
              onClick={() => copyToClipboard(body, 'body')}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
            >
              {copiedBody ? <Check className="h-3 w-3 text-green-600" /> : <Copy className="h-3 w-3" />}
              {copiedBody ? 'Kopiert!' : 'Kopieren'}
            </button>
          </div>
          <pre className="p-3 bg-gray-50 rounded border text-sm whitespace-pre-wrap font-sans max-h-64 overflow-y-auto">
            {body}
          </pre>
        </div>

        {/* Actions */}
        <div className="flex gap-2 pt-2">
          <button
            onClick={() => copyToClipboard(`${subject}\n\n${body}`, 'all')}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            {copiedAll ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copiedAll ? 'Kopiert!' : 'Alles kopieren'}
          </button>
          <button
            onClick={handleDownloadEml}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
          >
            <Download className="h-4 w-4" />
            .eml herunterladen
          </button>
          <a
            href={`mailto:${CONFIG.recipientEmail}?cc=${CONFIG.ccEmail}&subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
          >
            <Mail className="h-4 w-4" />
            In Mail öffnen
          </a>
        </div>
      </div>
    </div>
  )
}

export default function Reminders() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['receipts-for-reminders'],
    queryFn: () => receiptsApi.list({ status: 'submitted', limit: 100 }),
  })

  // Separate overdue and soon-due receipts
  const { overdueGroups, soonDueGroups } = useMemo(() => {
    if (!data?.receipts) return { overdueGroups: [], soonDueGroups: [] }

    // Filter to only pending reimbursement
    const pending = data.receipts.filter(r =>
      r.status === 'submitted'
    )

    const today = new Date()

    const overdue = pending.filter(r => {
      const deadline = getDeadlineDate(r.submission_date)
      return deadline < today
    })

    const soonDue = pending.filter(r => {
      const deadline = getDeadlineDate(r.submission_date)
      const daysUntil = Math.floor((deadline.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
      return daysUntil >= 0 && daysUntil <= 7 // Due within 7 days
    })

    return {
      overdueGroups: groupReceiptsBySubmission(overdue),
      soonDueGroups: groupReceiptsBySubmission(soonDue),
    }
  }, [data])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
        Fehler beim Laden der Daten: {error instanceof Error ? error.message : 'Unbekannter Fehler'}
      </div>
    )
  }

  const totalOverdue = overdueGroups.length
  const totalSoonDue = soonDueGroups.length
  const hasContent = totalOverdue > 0 || totalSoonDue > 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Mahnungen</h1>
          <p className="mt-1 text-sm text-gray-500">
            Erstattungs-Erinnerungen an die Universa gemäß § 14 VVG
          </p>
        </div>
        <div className="flex items-center gap-4 text-sm">
          {totalOverdue > 0 && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-red-100 text-red-700 rounded-full">
              <AlertTriangle className="h-4 w-4" />
              {totalOverdue} überfällig
            </div>
          )}
          {totalSoonDue > 0 && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-yellow-100 text-yellow-700 rounded-full">
              <Clock className="h-4 w-4" />
              {totalSoonDue} bald fällig
            </div>
          )}
        </div>
      </div>

      {!hasContent ? (
        <div className="bg-green-50 border border-green-200 rounded-lg p-8 text-center">
          <FileText className="h-12 w-12 mx-auto text-green-500 mb-3" />
          <h3 className="text-lg font-medium text-green-800">Keine Mahnungen erforderlich</h3>
          <p className="mt-1 text-sm text-green-600">
            Alle eingereichten Belege sind innerhalb der gesetzlichen Frist.
          </p>
        </div>
      ) : (
        <>
          {/* Overdue Section */}
          {overdueGroups.length > 0 && (
            <section>
              <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-red-600" />
                Überfällige Erstattungen
                <span className="text-sm font-normal text-gray-500">
                  (Frist abgelaufen, Mahnung mit Fristsetzung)
                </span>
              </h2>
              <div className="space-y-4">
                {overdueGroups.map((group) => (
                  <EmailCard key={group.submissionDate} group={group} isOverdue={true} />
                ))}
              </div>
            </section>
          )}

          {/* Soon Due Section */}
          {soonDueGroups.length > 0 && (
            <section className={overdueGroups.length > 0 ? 'mt-8' : ''}>
              <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                <Clock className="h-5 w-5 text-yellow-600" />
                Bald fällige Erstattungen
                <span className="text-sm font-normal text-gray-500">
                  (Frist läuft in ≤7 Tagen ab, freundliche Erinnerung)
                </span>
              </h2>
              <div className="space-y-4">
                {soonDueGroups.map((group) => (
                  <EmailCard key={group.submissionDate} group={group} isOverdue={false} />
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {/* Info Box */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mt-8">
        <h3 className="font-medium text-blue-800 mb-2">Hinweise zu § 14 VVG</h3>
        <ul className="text-sm text-blue-700 space-y-1">
          <li>• <strong>Fälligkeit:</strong> Die Erstattung wird fällig, sobald die Versicherung die notwendigen Prüfungen abgeschlossen hat (§ 14 Abs. 1 VVG)</li>
          <li>• <strong>Monatsfrist:</strong> Ist die Prüfung einen Monat nach Einreichung nicht abgeschlossen, greift Abs. 2 (eine gesetzliche Höchstfrist für die Prüfung gibt es nicht)</li>
          <li>• <strong>Abschlagszahlung:</strong> Dann kann ein Abschlag in Höhe des voraussichtlichen Mindestbetrags verlangt werden (§ 14 Abs. 2 VVG)</li>
        </ul>
      </div>
    </div>
  )
}
