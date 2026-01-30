import { Outlet } from '@tanstack/react-router'
import { DashboardLayout } from '@/components/dashboard-layout'

export function NotFound() {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center bg-background p-4">
      <p className="text-muted-foreground">Not found</p>
    </div>
  )
}

export function LayoutComponent() {
  return (
    <DashboardLayout>
      <Outlet />
    </DashboardLayout>
  )
}
