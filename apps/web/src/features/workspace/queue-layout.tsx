import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '@/components/ui/resizable'

export function QueueLayout({
  list,
  detail,
}: {
  list: React.ReactNode
  detail: React.ReactNode
}) {
  return (
    <ResizablePanelGroup direction='horizontal' className='h-full min-w-0'>
      <ResizablePanel defaultSize={32} minSize={24} maxSize={45}>
        {list}
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel minSize={45}>{detail}</ResizablePanel>
    </ResizablePanelGroup>
  )
}
