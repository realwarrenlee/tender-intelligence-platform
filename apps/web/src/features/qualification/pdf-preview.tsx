import { useEffect, useRef, useState } from 'react'
import type {
  PDFDocumentLoadingTask,
  PDFDocumentProxy,
  RenderTask,
} from 'pdfjs-dist'

export function PdfPreview({
  file,
  initialPage = 1,
}: {
  file: Blob
  initialPage?: number
}) {
  const [document, setDocument] = useState<{
    pdf: PDFDocumentProxy
    aspectRatio: number
  }>()
  const [width, setWidth] = useState(0)
  const [error, setError] = useState('')
  const container = useRef<HTMLDivElement>(null)
  const selectedPage = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let active = true
    let loading: PDFDocumentLoadingTask | undefined
    void (async () => {
      const library = await import('pdfjs-dist')
      library.GlobalWorkerOptions.workerSrc = new URL(
        'pdfjs-dist/build/pdf.worker.min.mjs',
        import.meta.url
      ).toString()
      const data = await file.arrayBuffer()
      if (!active) return
      loading = library.getDocument({ data })
      const pdf = await loading.promise
      const first = (await pdf.getPage(1)).getViewport({ scale: 1 })
      if (active) setDocument({ pdf, aspectRatio: first.width / first.height })
    })().catch(() => {
      if (active)
        setError('This PDF could not be displayed. Try reopening the source.')
    })
    return () => {
      active = false
      void loading?.destroy()
    }
  }, [file])

  useEffect(() => {
    const element = container.current
    if (!element) return
    const observer = new ResizeObserver(() => setWidth(element.clientWidth))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (document && initialPage > 1)
      selectedPage.current?.scrollIntoView({ block: 'start' })
  }, [document, initialPage])

  return (
    <div ref={container} className='min-w-0 space-y-2'>
      {!document && !error && (
        <p role='status' className='p-4 text-base text-muted-foreground'>
          Rendering document…
        </p>
      )}
      {error && (
        <p role='alert' className='p-4 text-base text-red-500'>
          {error}
        </p>
      )}
      {document &&
        Array.from({ length: document.pdf.numPages }, (_, index) => (
          <div
            key={index}
            ref={
              index + 1 === Math.min(initialPage, document.pdf.numPages)
                ? selectedPage
                : undefined
            }
          >
            <PdfPage
              pdf={document.pdf}
              page={index + 1}
              width={width}
              initialAspectRatio={document.aspectRatio}
            />
          </div>
        ))}
    </div>
  )
}

function PdfPage({
  pdf,
  page,
  width,
  initialAspectRatio,
}: {
  pdf: PDFDocumentProxy
  page: number
  width: number
  initialAspectRatio: number
}) {
  const container = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const [visible, setVisible] = useState(false)
  const [aspectRatio, setAspectRatio] = useState(initialAspectRatio)
  const [renderedWidth, setRenderedWidth] = useState(0)
  const [error, setError] = useState('')
  const ready = !!width && renderedWidth === width

  useEffect(() => {
    const element = container.current
    if (!element) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) setRenderedWidth(0)
        setVisible(entry.isIntersecting)
      },
      { root: element.closest('[data-source-scroll]'), rootMargin: '800px 0px' }
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!visible || !width || !canvas.current) return
    let active = true
    let rendering: RenderTask | undefined
    const element = canvas.current
    void (async () => {
      const documentPage = await pdf.getPage(page)
      if (!active) return
      const natural = documentPage.getViewport({ scale: 1 })
      setAspectRatio(natural.width / natural.height)
      const viewport = documentPage.getViewport({
        scale: width / natural.width,
      })
      const density = Math.min(window.devicePixelRatio || 1, 2)
      element.width = Math.ceil(viewport.width * density)
      element.height = Math.ceil(viewport.height * density)
      rendering = documentPage.render({
        canvas: element,
        viewport,
        transform: [density, 0, 0, density, 0, 0],
      })
      await rendering.promise
      if (active) {
        setRenderedWidth(width)
        setError('')
      }
    })().catch(() => {
      if (active)
        setError('This page could not be displayed. Try reopening the source.')
    })
    return () => {
      active = false
      rendering?.cancel()
    }
  }, [pdf, page, width, visible])

  return (
    <div
      ref={container}
      role='group'
      aria-label={'PDF page ' + page}
      className='relative w-full bg-white'
      style={{ aspectRatio }}
    >
      {visible && !ready && !error && (
        <p role='status' className='p-4 text-base text-neutral-600'>
          Rendering page…
        </p>
      )}
      {error && (
        <p role='alert' className='p-4 text-base text-red-600'>
          {error}
        </p>
      )}
      {visible && (
        <canvas
          ref={canvas}
          role='img'
          aria-label={'Tender document page ' + page}
          className={
            ready && !error
              ? 'absolute inset-0 block h-full w-full'
              : 'invisible absolute inset-0'
          }
        />
      )}
    </div>
  )
}
