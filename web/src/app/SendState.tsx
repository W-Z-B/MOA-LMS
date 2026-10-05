import { useSendState, usePending } from "./offlineQueue";

/** Beside a write kept without a connection: "Waiting to send", then "Sent", or why it was not taken (item 4.02). */
export function SendState({ id }: { id: string | null }) {
  const state = useSendState(id);
  if (state === null) return null;
  if (state.state === "waiting")
    return (
      <span role="status" className="sync waiting">
        Waiting to send. It is sent when the connection returns.
      </span>
    );
  if (state.state === "sent")
    return (
      <span role="status" className="sync sent">
        Sent
      </span>
    );
  return (
    <span role="alert" className="sync refused">
      Not sent: {state.detail}
    </span>
  );
}

/** In the header: how many writes wait on this device for a connection. Nothing when none do. */
export function PendingCount() {
  const items = usePending();
  if (items.length === 0) return null;
  return (
    <span className="sync waiting" role="status" title={items.map((i) => i.label).join("\n")}>
      {items.length} waiting to send
    </span>
  );
}
