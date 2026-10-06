/** Moments as a datetime-local field shows them, on this device's clock (America/Guyana at GSA). */

/** An ISO moment as a datetime-local value on this device: 2027-01-12T09:00. */
export function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const at = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

/** A datetime-local value as an ISO moment, or null when it is empty. */
export function fromLocalInput(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}
