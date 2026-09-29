/**
 * Utility functions for the frontend
 */

/**
 * Format a date string to DD.MM.YYYY with leading zeros
 * @param dateStr - ISO date string or null
 * @returns Formatted date string or '-' if null
 */
export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  const day = String(d.getDate()).padStart(2, '0')
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const year = d.getFullYear()
  return `${day}.${month}.${year}`
}

/**
 * Format a number as currency (EUR)
 * @param amount - Number or null
 * @returns Formatted currency string or '-' if null
 */
export function formatCurrency(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return '-'
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount)
}

/**
 * Extract person name from bank transaction description
 * Often includes the family name or a first name. Names come from VITE_PERSON_NAMES
 * (comma-separated, e.g. "BEISPIEL,JONAS,MIRIAM,MILA,BEN,HELGA").
 * @param description - Bank transaction description
 * @returns Extracted name or null
 */
export function extractPersonFromDescription(description: string): string | null {
  if (!description) return null
  const upperDesc = description.toUpperCase()

  // Known family names, configured per installation
  const names = String(import.meta.env.VITE_PERSON_NAMES || '')
    .split(',')
    .map((n) => n.trim().toUpperCase())
    .filter(Boolean)
  for (const name of names) {
    if (upperDesc.includes(name)) {
      return name.charAt(0) + name.slice(1).toLowerCase()
    }
  }
  return null
}
