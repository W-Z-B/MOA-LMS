/** Small components the insight screens share. */

/** What is loading, or why it did not load. */
export function Waiting({ error }: { error: string | null }) {
  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  return <p className="loading">Loading…</p>;
}

/** A figure in a report: hidden where its group is too small (item 6.06). */
export function Figure({ value, hidden }: { value: number | string | null; hidden: boolean }) {
  if (hidden && value == null) return <span className="muted">Hidden</span>;
  return <>{value ?? "–"}</>;
}
