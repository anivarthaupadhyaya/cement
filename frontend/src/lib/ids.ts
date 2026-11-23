/** Random id for idempotent saves. crypto.randomUUID() only exists on https/localhost, and the
 * shop LAN is plain http, so fall back to getRandomValues (available everywhere). */
export function newClientRef(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}
