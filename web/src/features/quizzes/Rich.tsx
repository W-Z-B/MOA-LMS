import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * Question text, choices and feedback arrive as HTML cleaned on the server against the course pages'
 * allow-list (quizzes.api.rich, courses.richtext): no script, no event handlers, links to web addresses and
 * e-mail only. So it is placed in the page as it is, never cleaned again here.
 */
export function Rich({ html, inline = false, className }: { html: string; inline?: boolean; className?: string }) {
  const Tag = inline ? "span" : "div";
  return <Tag className={["rich", inline ? "rich-inline" : "", className ?? ""].join(" ").trim()} dangerouslySetInnerHTML={{ __html: html }} />;
}

/** Fill in the blanks: the gaps written [[1]], [[2]] ... become the inputs `gap` returns, in place in the text. */
export function ClozeText({ html, gap }: { html: string; gap: (key: string) => ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const [slots, setSlots] = useState<{ key: string; node: Element }[]>([]);
  // Only a fixed element is put in place of each gap marker, so the cleaned HTML stays as safe as it was.
  const marked = html.replace(/\[\[(\d{1,3})\]\]/g, '<span class="gap" data-gap="$1"></span>');
  useLayoutEffect(() => {
    const nodes = box.current ? Array.from(box.current.querySelectorAll("[data-gap]")) : [];
    setSlots(nodes.map((node) => ({ key: node.getAttribute("data-gap") ?? "", node })));
  }, [marked]);
  return (
    <>
      <div ref={box} className="rich" dangerouslySetInnerHTML={{ __html: marked }} />
      {slots.map((slot) => createPortal(gap(slot.key), slot.node, slot.key))}
    </>
  );
}
