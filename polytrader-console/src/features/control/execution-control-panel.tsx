/**
 * Execution control panel — Switch toggles for execution layers.
 *
 * Per PILOT_LIVE.md §5.1 / §5.3 / §8.4: Defense-in-depth execution
 * control with typed confirmation for critical actions.
 *
 * Layers:
 * 1. Execution Enabled — toggleable with typed confirmation
 * 2. Kill Switch — toggleable with typed confirmation (destructive)
 * 3. Circuit Breaker — read-only display
 */

import { useState } from 'react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { TypedAlertDialog } from '@/components/shared/typed-alert-dialog'
import {
  useExecutionStateQuery,
  useEnableExecutionMutation,
  useDisableExecutionMutation,
  useKillSwitchMutation,
  useKillSwitchResetMutation,
} from '@/hooks/use-execution-state'

function formatTimestamp(ts: string | undefined): string {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
}

export function ExecutionControlPanel() {
  const { data, isLoading } = useExecutionStateQuery()
  const enableExecution = useEnableExecutionMutation()
  const disableExecution = useDisableExecutionMutation()
  const killSwitch = useKillSwitchMutation()
  const killSwitchReset = useKillSwitchResetMutation()

  const [enableDialogOpen, setEnableDialogOpen] = useState(false)
  const [disableDialogOpen, setDisableDialogOpen] = useState(false)
  const [killDialogOpen, setKillDialogOpen] = useState(false)
  const [killResetDialogOpen, setKillResetDialogOpen] = useState(false)

  const executionEnabled = data?.execution_enabled ?? false
  const killSwitchActive = data?.kill_switch_active ?? false

  const handleExecutionToggle = () => {
    if (executionEnabled) {
      setDisableDialogOpen(true)
    } else {
      setEnableDialogOpen(true)
    }
  }

  const handleKillSwitchToggle = () => {
    if (killSwitchActive) {
      setKillResetDialogOpen(true)
    } else {
      setKillDialogOpen(true)
    }
  }

  return (
    <>
      <Card data-testid="execution-control-panel">
        <CardHeader>
          <CardTitle>Execution Controls</CardTitle>
          <CardDescription>
            Defense-in-depth layers controlling whether live orders can be placed.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          {/* Execution Enabled */}
          <div
            className="flex items-center justify-between gap-4"
            data-testid="execution-switch-row"
          >
            <div className="grid gap-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">Execution Enabled</span>
                <Badge variant={executionEnabled ? 'destructive' : 'secondary'}>
                  {executionEnabled ? 'ON' : 'OFF'}
                </Badge>
              </div>
              <p className="text-muted-foreground text-xs">
                Allow live orders to be placed on venues
              </p>
              {data && (
                <p className="text-muted-foreground text-xs">
                  v{data.version} · {formatTimestamp(data.updated_at)} · {data.updated_by}
                </p>
              )}
            </div>
            <Switch
              checked={executionEnabled}
              onCheckedChange={handleExecutionToggle}
              disabled={isLoading}
              data-testid="execution-switch"
              aria-label="Toggle execution"
            />
          </div>

          {/* Kill Switch */}
          <div className="flex items-center justify-between gap-4" data-testid="kill-switch-row">
            <div className="grid gap-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">Kill Switch</span>
                <Badge variant={killSwitchActive ? 'destructive' : 'outline'}>
                  {killSwitchActive ? 'ACTIVE' : 'READY'}
                </Badge>
              </div>
              <p className="text-muted-foreground text-xs">
                Emergency stop — disables all execution immediately
              </p>
              {killSwitchActive && data?.reason && (
                <p className="text-muted-foreground text-xs">Reason: {data.reason}</p>
              )}
            </div>
            <Switch
              checked={killSwitchActive}
              onCheckedChange={handleKillSwitchToggle}
              disabled={isLoading}
              data-testid="kill-switch-toggle"
              aria-label="Toggle kill switch"
            />
          </div>

          {/* Circuit Breaker — read-only */}
          <div
            className="flex items-center justify-between gap-4"
            data-testid="circuit-breaker-row"
          >
            <div className="grid gap-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">Circuit Breaker</span>
                <Badge variant="outline">OK</Badge>
              </div>
              <p className="text-muted-foreground text-xs">
                Automatic halt on reconciliation divergence
              </p>
            </div>
            {/* Circuit breaker is not user-toggleable — it triggers automatically */}
            <Switch checked={false} disabled aria-label="Circuit breaker status" />
          </div>
        </CardContent>
      </Card>

      {/* Enable Execution — typed "ENABLE LIVE" */}
      <TypedAlertDialog
        open={enableDialogOpen}
        onOpenChange={setEnableDialogOpen}
        title="Enable Execution"
        description="This will allow live orders to be placed on venues. Ensure all health gates are passing before enabling."
        confirmLabel="Enable Execution"
        confirmWord="ENABLE LIVE"
        isPending={enableExecution.isPending}
        onConfirm={() => {
          enableExecution.mutate(
            { reason: 'Execution enabled from control page' },
            { onSuccess: () => setEnableDialogOpen(false) },
          )
        }}
      />

      {/* Disable Execution — standard confirm */}
      <TypedAlertDialog
        open={disableDialogOpen}
        onOpenChange={setDisableDialogOpen}
        title="Disable Execution"
        description="This will prevent new orders from being placed. Existing open orders will not be cancelled."
        confirmLabel="Disable Execution"
        isPending={disableExecution.isPending}
        onConfirm={() => {
          disableExecution.mutate(
            { reason: 'Execution disabled from control page' },
            { onSuccess: () => setDisableDialogOpen(false) },
          )
        }}
      />

      {/* Kill Switch Activate — typed "KILL", destructive */}
      <TypedAlertDialog
        open={killDialogOpen}
        onOpenChange={setKillDialogOpen}
        title="Activate Kill Switch"
        description="This will immediately disable all execution and cancel open orders. This is an emergency action."
        confirmLabel="Activate Kill Switch"
        confirmWord="KILL"
        variant="destructive"
        isPending={killSwitch.isPending}
        onConfirm={() => {
          killSwitch.mutate(
            { reason: 'Kill switch activated from control page', cancelOpenOrders: true },
            { onSuccess: () => setKillDialogOpen(false) },
          )
        }}
      />

      {/* Kill Switch Reset — standard confirm */}
      <TypedAlertDialog
        open={killResetDialogOpen}
        onOpenChange={setKillResetDialogOpen}
        title="Reset Kill Switch"
        description="This will clear the kill switch state. Execution will remain disabled — you must re-enable it separately."
        confirmLabel="Reset Kill Switch"
        isPending={killSwitchReset.isPending}
        onConfirm={() => {
          killSwitchReset.mutate(
            { reason: 'Kill switch reset from control page' },
            { onSuccess: () => setKillResetDialogOpen(false) },
          )
        }}
      />
    </>
  )
}
