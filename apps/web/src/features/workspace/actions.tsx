import { cloneElement, useId, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ApiError } from './api'

export function useAction(onChange?: () => void) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uncertain, setUncertain] = useState(false)
  const retry = useRef<(() => Promise<void>) | null>(null)
  const active = useRef(false)
  async function execute(action: () => Promise<void>) {
    active.current = true
    setBusy(true)
    setError(null)
    try {
      await action()
      retry.current = null
      setUncertain(false)
    } catch (e) {
      const unknown = !(e instanceof ApiError) || e.retryable
      retry.current = unknown ? action : null
      setUncertain(unknown)
      setError(
        e instanceof ApiError
          ? e.message
          : 'Connection interrupted. The outcome is unknown; retry the same request safely.'
      )
      if (e instanceof ApiError && e.status === 409) onChange?.()
    } finally {
      active.current = false
      setBusy(false)
    }
  }
  return {
    busy,
    error,
    uncertain,
    run: (action: () => Promise<void>) => {
      if (!active.current && !retry.current) void execute(action)
    },
    retry: () => {
      if (retry.current && !active.current) void execute(retry.current)
    },
  }
}
export type Action = ReturnType<typeof useAction>
export function ActionError({ action }: { action: Action }) {
  if (!action.error) return null
  return (
    <div
      role='alert'
      className='my-3 flex flex-wrap items-center gap-2 border-l-2 border-destructive/40 py-2 pl-3 text-sm text-destructive'
    >
      {action.error}
      {action.uncertain && (
        <Button
          type='button'
          variant='outline'
          size='sm'
          onClick={action.retry}
          disabled={action.busy}
        >
          Retry same request
        </Button>
      )}
    </div>
  )
}
export function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactElement<{ id?: string }>
}) {
  const id = useId()
  return (
    <div className='grid min-w-0 gap-1.5 text-sm font-medium'>
      <label htmlFor={id}>{label}</label>
      {cloneElement(children, { id })}
    </div>
  )
}
export const selectStyle =
  'h-9 w-full min-w-0 rounded-md border bg-background px-3 text-sm'
