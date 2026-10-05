import { useEffect, type ReactNode } from "react";

interface Props {
  label: string;
  /** On a phone the panel rises from the bottom as a sheet; on a wider screen it drops from the header. */
  phone: boolean;
  onClose: () => void;
  children: ReactNode;
}

/** A panel opened from a header button: closed by Esc, or a click or tap anywhere outside it. */
export function Popover({ label, phone, onClose, children }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <div className={phone ? "popover-backdrop sheet" : "popover-backdrop"} onClick={onClose} aria-hidden="true" />
      <div className={phone ? "popover sheet" : "popover"} role="dialog" aria-label={label}>
        {phone && <span className="sheet-handle" aria-hidden="true" />}
        {children}
      </div>
    </>
  );
}
