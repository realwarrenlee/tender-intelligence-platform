import { useEffect, useRef, useState } from 'react'
import type { WorkBook } from 'xlsx'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export function DocxPreview({ file }: { file: Blob }) {
  const frame = useRef<HTMLIFrameElement>(null)
  const [error, setError] = useState(false)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!ready) return
    let active = true
    void (async () => {
      const { renderAsync } = await import('docx-preview')
      const document = frame.current?.contentDocument
      if (!document || !active) return
      await renderAsync(file, document.body, document.head, {
        renderAltChunks: false,
        useBase64URL: true,
      })
    })().catch(() => {
      if (active) setError(true)
    })
    return () => {
      active = false
    }
  }, [file, ready])

  return error ? (
    <p role='alert' className='p-4'>
      This document could not be displayed. Use extracted text instead.
    </p>
  ) : (
    <iframe
      ref={frame}
      onLoad={() => setReady(true)}
      title='Word document preview'
      sandbox='allow-same-origin'
      className='h-full min-h-[600px] w-full bg-white'
      srcDoc={
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data: blob:; font-src data: blob:; style-src \'unsafe-inline\'">'
      }
    />
  )
}

export function SpreadsheetPreview({ file }: { file: Blob }) {
  const [workbook, setWorkbook] = useState<WorkBook>()
  const [sheet, setSheet] = useState('')
  const [row, setRow] = useState(0)
  const [column, setColumn] = useState(0)
  const [error, setError] = useState(false)
  const [library, setLibrary] = useState<typeof import('xlsx')>()

  useEffect(() => {
    let active = true
    void (async () => {
      const xlsx = await import('xlsx')
      const book = xlsx.read(await file.arrayBuffer())
      if (active) {
        setLibrary(xlsx)
        setWorkbook(book)
        setSheet(book.SheetNames[0] || '')
      }
    })().catch(() => {
      if (active) setError(true)
    })
    return () => {
      active = false
    }
  }, [file])

  if (error)
    return (
      <p role='alert' className='p-4'>
        This spreadsheet could not be displayed. Use extracted text instead.
      </p>
    )
  if (!workbook || !library)
    return (
      <p role='status' className='p-4'>
        Loading spreadsheet…
      </p>
    )
  const worksheet = workbook.Sheets[sheet]
  const empty = !worksheet?.['!ref']
  const range = library.utils.decode_range(worksheet?.['!ref'] || 'A1:A1')
  const lastRow = Math.min(range.e.r, range.s.r + row + 99)
  const lastColumn = Math.min(range.e.c, range.s.c + column + 29)
  const rows = Array.from(
    { length: lastRow - range.s.r - row + 1 },
    (_, i) => range.s.r + row + i
  )
  const columns = Array.from(
    { length: lastColumn - range.s.c - column + 1 },
    (_, i) => range.s.c + column + i
  )

  return (
    <div className='p-4'>
      <div className='flex min-w-0 items-center gap-2'>
        <span>Sheet</span>
        <Select
          value={sheet}
          onValueChange={(value) => {
            setSheet(value)
            setRow(0)
            setColumn(0)
          }}
        >
          <SelectTrigger aria-label='Sheet' className='max-w-full min-w-0'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {workbook.SheetNames.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {empty ? (
        <p>This sheet is empty.</p>
      ) : (
        <>
          <div className='my-2 flex gap-2'>
            <button
              disabled={row === 0}
              onClick={() => setRow(Math.max(0, row - 100))}
            >
              Previous rows
            </button>
            <span>
              Rows {range.s.r + row + 1}–{lastRow + 1}
            </span>
            <button
              disabled={lastRow === range.e.r}
              onClick={() => setRow(row + 100)}
            >
              Next rows
            </button>
          </div>
          <div className='my-2 flex gap-2'>
            <button
              disabled={column === 0}
              onClick={() => setColumn(Math.max(0, column - 30))}
            >
              Previous columns
            </button>
            <span>
              Columns {library.utils.encode_col(range.s.c + column)}–
              {library.utils.encode_col(lastColumn)}
            </span>
            <button
              disabled={lastColumn === range.e.c}
              onClick={() => setColumn(column + 30)}
            >
              Next columns
            </button>
          </div>
          <div className='overflow-auto'>
            <table className='border-collapse text-sm'>
              <thead>
                <tr>
                  <th className='border p-1' />
                  {columns.map((c) => (
                    <th key={c} className='border p-1'>
                      {library.utils.encode_col(c)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r}>
                    <th className='border p-1'>{r + 1}</th>
                    {columns.map((c) => {
                      const cell =
                        worksheet[library.utils.encode_cell({ r, c })]
                      return (
                        <td
                          key={c}
                          className='min-w-24 border p-1 whitespace-pre-wrap'
                        >
                          {cell ? library.utils.format_cell(cell) : ''}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
