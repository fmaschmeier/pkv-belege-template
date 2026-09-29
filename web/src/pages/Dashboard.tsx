import { useQuery } from '@tanstack/react-query'
import { settlementsApi, bankApi } from '../lib/api'
import { formatDate, formatCurrency } from '../lib/utils'
import { FileText, CreditCard, TrendingUp, CheckCircle } from 'lucide-react'

function StatCard({ title, value, subtitle, icon: Icon, color }: {
  title: string
  value: string | number
  subtitle?: string
  icon: React.ElementType
  color: string
}) {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center">
        <div className={`p-3 rounded-full ${color}`}>
          <Icon className="h-6 w-6 text-white" />
        </div>
        <div className="ml-4">
          <p className="text-sm font-medium text-gray-500">{title}</p>
          <p className="text-2xl font-semibold text-gray-900">{value}</p>
          {subtitle && <p className="text-sm text-gray-500">{subtitle}</p>}
        </div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { data: settlementStats, isLoading: loadingSettlements } = useQuery({
    queryKey: ['settlementStats'],
    queryFn: () => settlementsApi.stats(),
  })

  const { data: bankStats, isLoading: loadingBank } = useQuery({
    queryKey: ['bankStats'],
    queryFn: () => bankApi.stats(),
  })

  const { data: settlements } = useQuery({
    queryKey: ['recentSettlements'],
    queryFn: () => settlementsApi.list({ limit: 5 }),
  })

  if (loadingSettlements || loadingBank) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Leistungsabrechnungen"
          value={settlementStats?.settlements_count || 0}
          subtitle={`${settlementStats?.items_count || 0} Positionen`}
          icon={FileText}
          color="bg-blue-500"
        />
        <StatCard
          title="Gesamt erstattet"
          value={formatCurrency(settlementStats?.total_reimbursed || 0)}
          icon={TrendingUp}
          color="bg-green-500"
        />
        <StatCard
          title="Universa-Zahlungen"
          value={bankStats?.universa_payments || 0}
          subtitle={formatCurrency(bankStats?.universa_total_amount || 0)}
          icon={CreditCard}
          color="bg-purple-500"
        />
        <StatCard
          title="Zugeordnet"
          value={`${bankStats?.universa_matched || 0} / ${bankStats?.universa_payments || 0}`}
          subtitle={bankStats?.universa_unmatched === 0 ? 'Alle zugeordnet' : `${bankStats?.universa_unmatched} offen`}
          icon={CheckCircle}
          color={bankStats?.universa_unmatched === 0 ? 'bg-green-500' : 'bg-yellow-500'}
        />
      </div>

      {/* Recent Settlements */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-medium text-gray-900">Letzte Abrechnungen</h2>
        </div>
        <div className="divide-y divide-gray-200">
          {settlements?.settlements.map((settlement) => (
            <div key={settlement.id} className="px-6 py-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-900">
                  {settlement.settlement_number}
                </p>
                <p className="text-sm text-gray-500">
                  {formatDate(settlement.settlement_date)} · {settlement.settlement_items.length} Positionen
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm font-medium text-green-600">
                  {formatCurrency(settlement.total_reimbursed || 0)}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
