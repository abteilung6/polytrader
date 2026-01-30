'use client'

import * as React from 'react'
import { ResponsiveContainer, Tooltip } from 'recharts'
import { cn } from '@/lib/utils'

type TooltipPayloadItem = {
  name?: string
  value?: number
  dataKey?: string
  color?: string
  payload?: unknown
}

export type ChartConfig = {
  [k: string]: {
    label?: React.ReactNode
    color?: string
  }
}

type ChartContextValue = { config: ChartConfig }
const ChartContext = React.createContext<ChartContextValue | null>(null)

function useChart(): ChartContextValue {
  const context = React.useContext(ChartContext)
  if (!context) {
    throw new Error('useChart must be used within a ChartContainer')
  }
  return context
}

type ChartContainerProps = React.ComponentProps<'div'> & {
  config: ChartConfig
  children: React.ReactNode
}

const ChartContainer = React.forwardRef<HTMLDivElement, ChartContainerProps>(
  ({ id, className, children, config, style, ...props }, ref) => {
    const uniqueId = React.useId()
    const chartId = `chart-${(id ?? uniqueId).replace(/:/g, '')}`
    const colorVars = Object.entries(config)
      .filter(([, c]) => c.color)
      .map(([key, c]) => `--color-${key}: ${c.color};`)
      .join('\n')
    return (
      <ChartContext.Provider value={{ config }}>
        <div
          ref={ref}
          data-chart={chartId}
          className={cn('h-[200px] w-full', className)}
          style={style}
          {...props}
        >
          {colorVars ? <style>{`[data-chart=${chartId}]{${colorVars}}`}</style> : null}
          <ResponsiveContainer width="100%" height="100%" minHeight={200}>
            {children}
          </ResponsiveContainer>
        </div>
      </ChartContext.Provider>
    )
  },
)
ChartContainer.displayName = 'ChartContainer'

export const ChartTooltip = Tooltip

type ChartTooltipContentProps = React.ComponentProps<'div'> & {
  active?: boolean
  payload?: TooltipPayloadItem[]
  label?: string | number
  hideLabel?: boolean
  nameKey?: string
  labelKey?: string
}

const ChartTooltipContent = React.forwardRef<HTMLDivElement, ChartTooltipContentProps>(
  (
    {
      active,
      payload = [],
      label,
      className,
      hideLabel = false,
      nameKey,
      labelKey: _labelKey,
      ...props
    },
    ref,
  ) => {
    const { config } = useChart()
    const list = Array.isArray(payload) ? payload : []
    if (!active || list.length === 0) return null
    return (
      <div
        ref={ref}
        className={cn(
          'rounded-lg border border-border bg-background p-2 text-sm shadow-md',
          className,
        )}
        {...props}
      >
        {!hideLabel && label != null && (
          <p className="mb-1 font-medium text-foreground">{String(label)}</p>
        )}
        {list.map((item: TooltipPayloadItem) => {
          const key = nameKey ?? item.dataKey ?? item.name ?? 'value'
          const itemConfig = config[key]
          const displayName = itemConfig?.label ?? item.name ?? key
          const color = item.color ?? (itemConfig?.color ? `var(--color-${key})` : undefined)
          return (
            <div key={key} className="flex items-center gap-2">
              {color && (
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: color }}
                />
              )}
              <span className="text-muted-foreground">{displayName}</span>
              {item.value != null && (
                <span className="font-medium tabular-nums">
                  {typeof item.value === 'number'
                    ? item.value.toLocaleString()
                    : String(item.value)}
                </span>
              )}
            </div>
          )
        })}
      </div>
    )
  },
)
ChartTooltipContent.displayName = 'ChartTooltipContent'

export type { ChartTooltipContentProps }
export { ChartContainer, ChartTooltipContent }
