import { useEffect, useState } from "react";
import { get } from "../../api/client";
import type { Conversation } from "../../api/types-talk";

const POLL_MS = 60_000;

/** How many messages from others wait unread, across every conversation (item 4.11). */
function useUnreadMessages(path: string): number {
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    const load = () =>
      get<Conversation[]>("/conversations/")
        .then((list) => setUnread(list.reduce((sum, c) => sum + c.unread, 0)))
        .catch(() => undefined);
    load();
    const handle = setInterval(load, POLL_MS);
    return () => clearInterval(handle);
  }, [path]);
  return unread;
}

/** In the header beside notifications: Messages, with the unread count. */
export function MessagesLink({ path, onNavigate }: { path: string; onNavigate: (to: string) => void }) {
  const unread = useUnreadMessages(path);
  return (
    <a
      className="icon-button messages-link"
      href="#/messages"
      aria-label={`Messages, ${unread} unread`}
      aria-current={path.startsWith("/messages") ? "page" : undefined}
      onClick={(e) => {
        e.preventDefault();
        onNavigate("/messages");
      }}
    >
      <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
        <path
          fill="currentColor"
          d="M4 3h16a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H9l-5 4v-4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"
        />
      </svg>
      {unread > 0 && <span className="badge">{unread}</span>}
    </a>
  );
}
