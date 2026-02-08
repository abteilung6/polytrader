import * as React from 'react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Input } from '@/components/ui/input'

/**
 * Props for TypedAlertDialog — a confirmation dialog with optional typed confirmation.
 *
 * Two modes:
 * - Standard: Cancel/Confirm buttons, action enabled immediately.
 * - Typed confirmation: User must type `confirmWord` exactly (case-sensitive)
 *   before the action button becomes enabled. Used for critical, hard-to-reverse
 *   actions (enable execution, kill switch, activate for live).
 *
 * Per PILOT_LIVE.md §8.3: Standard for reversible actions, typed-confirm for
 * actions with immediate financial consequence.
 */
export interface TypedAlertDialogProps {
  /** Whether the dialog is open. */
  open: boolean
  /** Callback when open state changes (e.g., on cancel or overlay click). */
  onOpenChange: (open: boolean) => void
  /** Dialog title (e.g., "Enable Execution"). */
  title: string
  /** Dialog description — string or ReactNode for rich content. */
  description: string | React.ReactNode
  /** Label for the confirm/action button (e.g., "Enable Execution"). */
  confirmLabel: string
  /**
   * If set, enables typed confirmation mode: user must type this word
   * exactly (case-sensitive) before the action button becomes enabled.
   * Examples: "ENABLE LIVE", "ACTIVATE", "KILL".
   */
  confirmWord?: string
  /** Visual variant for the action button. */
  variant?: 'default' | 'destructive'
  /** Called when the user confirms the action. */
  onConfirm: () => void
  /** When true, shows a loading state on the action button and disables it. */
  isPending?: boolean
}

/**
 * Confirmation dialog with optional typed confirmation for critical actions.
 *
 * Wraps shadcn AlertDialog. When `confirmWord` is provided, renders an Input
 * field that must match exactly before the action button is enabled.
 */
export function TypedAlertDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  confirmWord,
  variant = 'default',
  onConfirm,
  isPending = false,
}: TypedAlertDialogProps) {
  const [typedValue, setTypedValue] = React.useState('')

  // Reset typed value when dialog opens/closes
  React.useEffect(() => {
    if (!open) {
      setTypedValue('')
    }
  }, [open])

  const isTypedMode = confirmWord !== undefined && confirmWord.length > 0
  const isConfirmEnabled = isTypedMode ? typedValue === confirmWord : true
  const isActionDisabled = !isConfirmEnabled || isPending

  const handleConfirm = (e: React.MouseEvent) => {
    // Prevent default AlertDialogAction close behavior when disabled
    if (isActionDisabled) {
      e.preventDefault()
      return
    }
    onConfirm()
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription asChild={typeof description !== 'string'}>
            {typeof description === 'string' ? description : <div>{description}</div>}
          </AlertDialogDescription>
        </AlertDialogHeader>

        {isTypedMode && (
          <div className="grid gap-2">
            <label htmlFor="typed-confirm-input" className="text-muted-foreground text-sm">
              Type <span className="text-foreground font-mono font-semibold">{confirmWord}</span> to
              confirm
            </label>
            <Input
              id="typed-confirm-input"
              data-testid="typed-confirm-input"
              value={typedValue}
              onChange={(e) => setTypedValue(e.target.value)}
              placeholder={confirmWord}
              autoComplete="off"
              autoFocus
            />
          </div>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction variant={variant} disabled={isActionDisabled} onClick={handleConfirm}>
            {isPending ? (
              <>
                <span
                  className="border-background inline-block size-4 animate-spin rounded-full border-2 border-t-transparent"
                  role="status"
                  aria-label="Loading"
                />
                {confirmLabel}
              </>
            ) : (
              confirmLabel
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
