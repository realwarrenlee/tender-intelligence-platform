import { type ReactNode } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { type Action } from './actions'

export function TaskDialog({
  title,
  description,
  action,
  onClose,
  onReturnFocus,
  children,
}: {
  title: string
  description?: string
  action: Action
  onClose: () => void
  onReturnFocus: () => void
  children: ReactNode
}) {
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !action.busy && !action.uncertain) onClose()
      }}
    >
      <DialogContent
        className='max-h-[85vh] min-w-0 overflow-y-auto'
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          onReturnFocus()
        }}
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className={description ? '' : 'sr-only'}>
            {description || title}
          </DialogDescription>
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  )
}
