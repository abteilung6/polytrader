import { Fragment } from 'react'
import { Link, useParams, useRouterState } from '@tanstack/react-router'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { Separator } from '@/components/ui/separator'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { EnvironmentBadge } from '@/features/operations/environment-badge'
import { useStrategyDetailQuery } from '@/hooks/strategy-detail'

function useHeaderTitle(): { segments: { label: string; href?: string }[] } {
  const pathname = useRouterState({ select: (s) => s.location.pathname }) ?? ''
  const { marketSlug, strategyId } = useParams({ strict: false })

  const isInstanceDetail =
    pathname.startsWith('/strategies/instances/') &&
    pathname !== '/strategies/instances' &&
    !!strategyId
  const { data: strategy } = useStrategyDetailQuery(strategyId ?? '', {
    enabled: isInstanceDetail,
  })

  if (marketSlug && pathname.startsWith('/markets/')) {
    return {
      segments: [{ label: 'Markets', href: '/markets' }, { label: marketSlug }],
    }
  }
  if (isInstanceDetail) {
    return {
      segments: [
        { label: 'Strategy instances', href: '/strategies/instances' },
        { label: strategy?.name ?? strategyId ?? '' },
      ],
    }
  }
  if (pathname === '/control') {
    return { segments: [{ label: 'Control' }] }
  }
  if (pathname === '/performance/paper') {
    return {
      segments: [{ label: 'Performance', href: '/performance/paper' }, { label: 'Paper Trading' }],
    }
  }
  if (pathname === '/performance/live') {
    return {
      segments: [{ label: 'Performance', href: '/performance/paper' }, { label: 'Live Trading' }],
    }
  }
  if (pathname === '/strategies/templates') {
    return { segments: [{ label: 'Strategy templates' }] }
  }
  if (pathname === '/strategies/instances') {
    return { segments: [{ label: 'Strategy instances' }] }
  }
  if (pathname.startsWith('/markets')) {
    return { segments: [{ label: 'Markets' }] }
  }
  return { segments: [{ label: 'Polytrader' }] }
}

export function SiteHeader() {
  const { segments } = useHeaderTitle()

  return (
    <header className="flex h-[var(--header-height)] shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-[var(--header-height)]">
      <div className="flex w-full items-center gap-2 px-4 lg:px-6">
        <SidebarTrigger className="-ml-1" />
        <Separator orientation="vertical" className="mr-2 data-[orientation=vertical]:h-4" />
        <Breadcrumb>
          <BreadcrumbList>
            {segments.map((seg, i) => (
              <Fragment key={i}>
                {i > 0 && <BreadcrumbSeparator />}
                <BreadcrumbItem>
                  {seg.href != null ? (
                    <BreadcrumbLink asChild>
                      <Link to={seg.href}>{seg.label}</Link>
                    </BreadcrumbLink>
                  ) : (
                    <BreadcrumbPage>{seg.label}</BreadcrumbPage>
                  )}
                </BreadcrumbItem>
              </Fragment>
            ))}
          </BreadcrumbList>
        </Breadcrumb>
        <div className="ml-auto">
          <EnvironmentBadge />
        </div>
      </div>
    </header>
  )
}
