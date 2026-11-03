export const tenderFileTypes = '.pdf,.docx,.doc,.xlsx,.pptx'

export function tenderFileError(
  files: File[],
  existing: Array<{ filename: string; byte_size: number }>
) {
  if (files.some((file) => !/\.(pdf|docx|doc|xlsx|pptx)$/i.test(file.name)))
    return 'Choose PDF, Word, Excel or PowerPoint files.'
  if (files.some((file) => file.size > 20 * 1024 * 1024))
    return 'Each file must be 20 MiB or smaller.'
  if (
    files.length + existing.length > 100 ||
    files.reduce((size, file) => size + file.size, 0) +
      existing.reduce((size, file) => size + file.byte_size, 0) >
      100 * 1024 * 1024
  )
    return 'A tender pack can contain up to 100 files and 100 MiB.'
  const names = new Set<string>()
  for (const file of files) {
    const name = file.name.toLocaleLowerCase()
    if (names.has(name))
      return (
        'Two files share the name "' +
        file.name +
        '". Rename one before adding the pack.'
      )
    names.add(name)
  }
  return ''
}
