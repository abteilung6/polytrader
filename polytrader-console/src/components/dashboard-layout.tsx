import type { CSSProperties, ReactNode } from 'react'

import { AppSidebar } from '@/components/app-sidebar'
import { SiteHeader } from '@/components/site-header'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'

interface DashboardLayoutProps {
  children: ReactNode
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  return (
    <SidebarProvider
      style={
        {
          '--sidebar-width': '16rem',
          '--header-height': '3rem',
        } as CSSProperties
      }
    >
      <AppSidebar variant="inset" />
      <SidebarInset>
        <SiteHeader />
        <div className="flex flex-1 flex-col px-3 md:px-4">
          <div className="@container/main flex flex-1 flex-col gap-2">
            <div className="flex flex-col gap-2 py-2 md:gap-4 md:py-4">{children}</div>
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
