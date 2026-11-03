export function memberName(value: string) {
  return value.split('@')[0].trim() || 'Workspace member'
}
