'use client'

import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { BarChart3, ChevronDown, Shield, TrendingUp, Workflow } from 'lucide-react'

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail,
} from '@/components/ui/sidebar'
import { cn } from '@/lib/utils'

interface AppSidebarProps {
  variant?: 'sidebar' | 'floating' | 'inset'
}

export function AppSidebar({ variant = 'inset' }: AppSidebarProps) {
  const [strategiesOpen, setStrategiesOpen] = useState(true)

  return (
    <Sidebar collapsible="icon" variant={variant}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild className="data-[slot=sidebar-menu-button]:!p-1.5">
              <Link to="/">
                <span className="text-base font-semibold">Polytrader</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent className="flex flex-col gap-2">
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="Control">
                  <Link to="/control">
                    <Shield />
                    <span>Control</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="Performance">
                  <Link to="/performance">
                    <TrendingUp />
                    <span>Performance</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="Markets">
                  <Link to="/markets">
                    <BarChart3 />
                    <span>Markets</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Strategies"
                  className="cursor-pointer"
                  onClick={() => setStrategiesOpen((open) => !open)}
                >
                  <Workflow />
                  <span>Strategies</span>
                  <ChevronDown
                    className={cn(
                      'ml-auto size-4 shrink-0 transition-transform',
                      !strategiesOpen && '-rotate-90',
                    )}
                    aria-hidden
                  />
                </SidebarMenuButton>
                {strategiesOpen && (
                  <SidebarMenuSub>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton asChild>
                        <Link to="/strategies/templates">
                          <span>Templates</span>
                        </Link>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton asChild>
                        <Link to="/strategies/instances">
                          <span>Instances</span>
                        </Link>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                  </SidebarMenuSub>
                )}
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  )
}
