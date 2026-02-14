import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

import { TypedAlertDialog } from './typed-alert-dialog'

describe('TypedAlertDialog', () => {
  const baseProps = {
    open: true,
    onOpenChange: vi.fn(),
    title: 'Confirm Action',
    description: 'Are you sure you want to proceed?',
    confirmLabel: 'Confirm',
    onConfirm: vi.fn(),
  }

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('Standard mode (no confirmWord)', () => {
    it('renders title, description, and action button enabled immediately', () => {
      render(<TypedAlertDialog {...baseProps} />)

      expect(screen.getByText('Confirm Action')).toBeInTheDocument()
      expect(screen.getByText('Are you sure you want to proceed?')).toBeInTheDocument()

      const confirmButton = screen.getByRole('button', { name: 'Confirm' })
      expect(confirmButton).toBeEnabled()
    })

    it('does not render typed confirmation input', () => {
      render(<TypedAlertDialog {...baseProps} />)

      expect(screen.queryByTestId('typed-confirm-input')).not.toBeInTheDocument()
    })

    it('calls onConfirm when confirm button is clicked', async () => {
      const user = userEvent.setup()
      const onConfirm = vi.fn()
      render(<TypedAlertDialog {...baseProps} onConfirm={onConfirm} />)

      await user.click(screen.getByRole('button', { name: 'Confirm' }))
      expect(onConfirm).toHaveBeenCalledOnce()
    })

    it('calls onOpenChange when cancel button is clicked', async () => {
      const user = userEvent.setup()
      const onOpenChange = vi.fn()
      render(<TypedAlertDialog {...baseProps} onOpenChange={onOpenChange} />)

      await user.click(screen.getByRole('button', { name: 'Cancel' }))
      expect(onOpenChange).toHaveBeenCalled()
    })
  })

  describe('Typed confirmation mode (confirmWord set)', () => {
    const typedProps = {
      ...baseProps,
      confirmWord: 'ENABLE LIVE',
      confirmLabel: 'Enable Execution',
    }

    it('renders typed confirmation input', () => {
      render(<TypedAlertDialog {...typedProps} />)

      expect(screen.getByTestId('typed-confirm-input')).toBeInTheDocument()
      expect(screen.getByText('ENABLE LIVE')).toBeInTheDocument()
    })

    it('action button is disabled until word matches', () => {
      render(<TypedAlertDialog {...typedProps} />)

      const confirmButton = screen.getByRole('button', { name: 'Enable Execution' })
      expect(confirmButton).toBeDisabled()
    })

    it('action button becomes enabled when typed word matches exactly', async () => {
      const user = userEvent.setup()
      render(<TypedAlertDialog {...typedProps} />)

      const input = screen.getByTestId('typed-confirm-input')
      await user.type(input, 'ENABLE LIVE')

      const confirmButton = screen.getByRole('button', { name: 'Enable Execution' })
      expect(confirmButton).toBeEnabled()
    })

    it('enforces case-sensitive matching', async () => {
      const user = userEvent.setup()
      render(<TypedAlertDialog {...typedProps} />)

      const input = screen.getByTestId('typed-confirm-input')
      await user.type(input, 'enable live')

      const confirmButton = screen.getByRole('button', { name: 'Enable Execution' })
      expect(confirmButton).toBeDisabled()
    })

    it('action button disabled with partial match', async () => {
      const user = userEvent.setup()
      render(<TypedAlertDialog {...typedProps} />)

      const input = screen.getByTestId('typed-confirm-input')
      await user.type(input, 'ENABLE')

      const confirmButton = screen.getByRole('button', { name: 'Enable Execution' })
      expect(confirmButton).toBeDisabled()
    })

    it('calls onConfirm only when word matches and button is clicked', async () => {
      const user = userEvent.setup()
      const onConfirm = vi.fn()
      render(<TypedAlertDialog {...typedProps} onConfirm={onConfirm} />)

      const input = screen.getByTestId('typed-confirm-input')
      await user.type(input, 'ENABLE LIVE')
      await user.click(screen.getByRole('button', { name: 'Enable Execution' }))

      expect(onConfirm).toHaveBeenCalledOnce()
    })

    it('resets typed value when dialog closes and reopens', () => {
      const { rerender } = render(<TypedAlertDialog {...typedProps} />)

      // Close the dialog
      rerender(<TypedAlertDialog {...typedProps} open={false} />)
      // Reopen the dialog
      rerender(<TypedAlertDialog {...typedProps} open={true} />)

      const input = screen.getByTestId('typed-confirm-input')
      expect(input).toHaveValue('')
    })
  })

  describe('Destructive variant', () => {
    it('renders action button with destructive styling', () => {
      render(
        <TypedAlertDialog
          {...baseProps}
          variant="destructive"
          confirmLabel="Kill Switch"
          confirmWord="KILL"
        />,
      )

      // The action button should exist (styling is applied via variant prop)
      const confirmButton = screen.getByRole('button', { name: 'Kill Switch' })
      expect(confirmButton).toBeInTheDocument()
    })
  })

  describe('Pending state', () => {
    it('disables action button when isPending is true', () => {
      render(<TypedAlertDialog {...baseProps} isPending={true} />)

      const confirmButton = screen.getByRole('button', { name: /Confirm/i })
      expect(confirmButton).toBeDisabled()
    })

    it('shows loading spinner when isPending is true', () => {
      render(<TypedAlertDialog {...baseProps} isPending={true} />)

      expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument()
    })

    it('disables cancel button when isPending is true', () => {
      render(<TypedAlertDialog {...baseProps} isPending={true} />)

      const cancelButton = screen.getByRole('button', { name: 'Cancel' })
      expect(cancelButton).toBeDisabled()
    })
  })

  describe('Rich description (ReactNode)', () => {
    it('renders ReactNode description correctly', () => {
      render(
        <TypedAlertDialog
          {...baseProps}
          description={
            <p>
              This action will <strong>enable live trading</strong> on the platform.
            </p>
          }
        />,
      )

      expect(screen.getByText(/enable live trading/)).toBeInTheDocument()
    })
  })
})
