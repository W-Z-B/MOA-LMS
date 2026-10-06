import { useEffect, useRef, useState } from "react";
import { announcement, formatLeft } from "./quizUtil";

interface Props {
  /** Seconds left by the server's clock when the attempt was last fetched or an answer was saved. */
  secondsLeft: number;
  /** This device's clock (ms) at that moment: the countdown runs from there, never from the device's date. */
  syncedAt: number;
  onExpire: () => void;
}

/**
 * Time left on an attempt, driven by the server's deadline (item 3.03). It is shown every second, but a
 * screen reader is told only twice: at five minutes and at one minute, not at every tick.
 */
export function Countdown({ secondsLeft, syncedAt, onExpire }: Props) {
  const [remaining, setRemaining] = useState(() => secondsLeft - (Date.now() - syncedAt) / 1000);
  const [announce, setAnnounce] = useState("");
  const said = useRef(new Set<number>());
  const expired = useRef(false);
  const expire = useRef(onExpire);
  useEffect(() => {
    expire.current = onExpire;
  }, [onExpire]);

  useEffect(() => {
    const tick = () => {
      const left = secondsLeft - (Date.now() - syncedAt) / 1000;
      setRemaining(left);
      if (left <= 0) {
        if (!expired.current) {
          expired.current = true;
          setAnnounce("Time is up. Your answers are being submitted.");
          expire.current();
        }
        return;
      }
      expired.current = false;
      const message = announcement(left, said.current);
      if (message) setAnnounce(message);
    };
    const first = window.setTimeout(tick, 0);
    const timer = window.setInterval(tick, 1000);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [secondsLeft, syncedAt]);

  const low = remaining <= 300;
  return (
    <div className={low ? "countdown low" : "countdown"}>
      <span className="countdown-label">Time left</span>
      {/* A timer is not read out as it changes; the message below is. */}
      <span role="timer" className="countdown-time num">
        {formatLeft(remaining)}
      </span>
      <span className="sr-only" aria-live="assertive">
        {announce}
      </span>
    </div>
  );
}
