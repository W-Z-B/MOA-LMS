/** The School's crest in its round frame. Decorative where the School's name is written beside it. */
export function Crest({ size, label }: { size: 32 | 40 | 72 | 140; label?: string }) {
  return (
    <span className={`crest crest-${size}`}>
      <img src="/crest.png" alt={label ?? ""} width={size} height={size} />
    </span>
  );
}
