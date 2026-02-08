/**
 * Live Trading dashboard — operational view for monitoring live strategies
 * and recent live orders. Tabs: Live strategies | Recent orders.
 */

import type { FC } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'

import { LiveOrdersTable } from '@/features/live-trading/live-orders-table'
import { LiveStrategiesTable } from '@/features/live-trading/live-strategies-table'
import { LiveSummaryCards } from '@/features/live-trading/live-summary-cards'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

type TabValue = 'strategies' | 'orders'

export const LiveTradingPage: FC = () => {
  const { tab: tabParam } = useSearch({ strict: false })
  const navigate = useNavigate()
  const activeTab: TabValue = tabParam === 'orders' ? 'orders' : 'strategies'

  const setTab = (value: string) => {
    const tab: TabValue = value === 'orders' ? 'orders' : 'strategies'
    void navigate({ to: '/performance/live', search: { tab } })
  }

  return (
    <div className="flex flex-col gap-6 p-4">
      <LiveSummaryCards />
      <Tabs value={activeTab} onValueChange={setTab} className="w-full flex-col gap-4">
        <TabsList>
          <TabsTrigger value="strategies">Live strategies</TabsTrigger>
          <TabsTrigger value="orders">Recent orders</TabsTrigger>
        </TabsList>
        <TabsContent value="strategies" className="flex flex-col gap-4">
          <LiveStrategiesTable />
        </TabsContent>
        <TabsContent value="orders" className="flex flex-col gap-4">
          <LiveOrdersTable />
        </TabsContent>
      </Tabs>
    </div>
  )
}
