import type { FC } from 'react'

import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { type WindowPreset, WINDOW_PRESETS } from '@/lib/window-presets'

interface WindowSelectorProps {
  value: WindowPreset
  onChange: (preset: WindowPreset) => void
}

export const WindowSelector: FC<WindowSelectorProps> = ({ value, onChange }) => {
  return (
    <Tabs value={value} onValueChange={(v) => onChange(v as WindowPreset)}>
      <TabsList>
        {WINDOW_PRESETS.map((preset) => (
          <TabsTrigger key={preset.value} value={preset.value}>
            {preset.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}
