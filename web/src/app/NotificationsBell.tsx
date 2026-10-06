import { useCallback, useEffect, useState } from "react";
import { get, post } from "../api/client";
import type { Notification } from "../api/types";
import { dmyTime } from "./format";
import { Popover } from "./Popover";

interface Props {
  open: boolean;
  phone: boolean;
  onToggle: () => void;
  onClose: () => void;
  onNavigate: (to: string) => void;
}

const POLL_MS = 60_000;

/** Unread count on the bell; opens the inbox (a sheet on phones), marks items read and follows their links. */
export function NotificationsBell({ open, phone, onToggle, onClose, onNavigate }: Props) {
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<Notification[]>([]);

  const load = useCallback(() => {
    get<{ unread: number; results: Notification[] }>("/notifications/")
      .then((r) => {
        setUnread(r.unread);
        setItems(r.results);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    load();
    const handle = setInterval(load, POLL_MS);
    return () => clearInterval(handle);
  }, [load]);

  async function openItem(item: Notification) {
    if (!item.read_at) await post(`/notifications/${item.id}/read/`).catch(() => undefined);
    onClose();
    load();
    if (item.link) onNavigate(item.link);
  }

  async function readAll() {
    await post("/notifications/read-all/").catch(() => undefined);
    load();
  }

  return (
    <div className="bell">
      <button
        className="icon-button"
        aria-expanded={open}
        aria-label={`Notifications, ${unread} unread`}
        onClick={onToggle}
      >
        <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
          <path
            fill="currentColor"
            d="M12 22a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22Zm7-6V11a7 7 0 0 0-5.5-6.84V3a1.5 1.5 0 0 0-3 0v1.16A7 7 0 0 0 5 11v5l-2 2v1h18v-1l-2-2Z"
          />
        </svg>
        {unread > 0 && <span className="badge">{unread}</span>}
      </button>
      {open && (
        <Popover label="Notifications" phone={phone} onClose={onClose}>
          <div className="popover-head">
            <strong>Notifications</strong>
            {unread > 0 && (
              <button className="link accent" onClick={readAll}>
                Mark all read
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <p className="muted popover-empty">Nothing yet.</p>
          ) : (
            <ul className="notes">
              {items.slice(0, 15).map((item) => (
                <li key={item.id} className={item.read_at ? "read" : "unread"}>
                  <button className="note" onClick={() => openItem(item)}>
                    <span className={`kind kind-${item.kind}`} aria-hidden="true" />
                    <span>
                      <span className="title">{item.title}</span>
                      <span className="muted small">{dmyTime(item.created_at)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Popover>
      )}
    </div>
  );
}
