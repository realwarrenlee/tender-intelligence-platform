import { cn } from '@/lib/utils'

const colors = {
  pursue:
    'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  hold: 'border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-400',
  decline: 'border-rose-500/25 bg-rose-500/10 text-rose-700 dark:text-rose-400',
}
export function DecisionBadge({
  decision,
}: {
  decision: 'pursue' | 'hold' | 'decline' | null
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-sm font-medium capitalize',
        decision ? colors[decision] : 'text-muted-foreground'
      )}
    >
      <span className='size-1.5 rounded-full bg-current' aria-hidden='true' />
      {decision || 'Not assessed'}
    </span>
  )
}
