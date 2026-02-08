/**
 * Live Trading dashboard — monitoring only: summary cards + tabbed content (Orders).
 * Manage who is active on Control (add from Strategy instances, remove via dropdown).
 * Future: add performance rows (live PnL per strategy).
 */

import { useState } from 'react'
import type { FC } from 'react'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { LiveOrdersTable } from '@/features/live-trading/live-orders-table'
import { LiveSummaryCards } from '@/features/live-trading/live-summary-cards'

export const LiveTradingPage: FC = () => {
  const [tab, setTab] = useState('orders')

  return (
    <div className="flex flex-col gap-6 p-4">
      <LiveSummaryCards />
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList>
          <TabsTrigger value="orders">Orders</TabsTrigger>
        </TabsList>
        <TabsContent value="orders" className="mt-4">
          <LiveOrdersTable />
        </TabsContent>
      </Tabs>
    </div>
  )
}
