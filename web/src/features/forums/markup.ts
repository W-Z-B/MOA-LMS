/**
 * Plain text with simple formatting for posts and messages (items 4.08, 4.11): **bold**, *italic*, a line
 * starting "- " for a list, [words](https://address) for a link, and a bare https address becomes a link. It
 * is turned into HTML here, and the server cleans whatever arrives against its allow-list (courses.richtext),
 * so nothing written here can put anything but these few tags on the page. No editor library: forums stay
 * light on a phone.
 */

const escape = (text: string) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const LINK = /\[([^\]\n]+)\]\(((?:https?:\/\/|mailto:)[^\s)]+)\)/g;
const BARE = /(^|[\s(])(https?:\/\/[^\s<]+[^\s<.,;:!?)])/g;

/** One line's words: links, then bold, then italic. The text is escaped first. */
function inline(text: string): string {
  return escape(text)
    .replace(LINK, (_, words: string, href: string) => `<a href="${href}">${words}</a>`)
    .replace(BARE, (_, before: string, href: string) => `${before}<a href="${href}">${href}</a>`)
    .replace(/\*\*(?=\S)(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*(?=\S)([^*]+?)\*(?!\*)/g, "$1<em>$2</em>");
}

const ITEM = /^\s*[-*]\s+/;

/** The text as HTML: paragraphs at blank lines, lists where lines start "- ", line breaks kept. */
export function toHtml(text: string): string {
  const blocks = text.replace(/\r\n/g, "\n").split(/\n\s*\n/);
  const out: string[] = [];
  for (const block of blocks) {
    const lines = block.split("\n").filter((line) => line.trim() !== "");
    let para: string[] = [];
    let list: string[] = [];
    const endPara = () => {
      if (para.length) out.push(`<p>${para.map(inline).join("<br>")}</p>`);
      para = [];
    };
    const endList = () => {
      if (list.length) out.push(`<ul>${list.map((item) => `<li>${inline(item)}</li>`).join("")}</ul>`);
      list = [];
    };
    for (const line of lines) {
      if (ITEM.test(line)) {
        endPara();
        list.push(line.replace(ITEM, ""));
      } else {
        endList();
        para.push(line.trim());
      }
    }
    endPara();
    endList();
  }
  return out.join("");
}

/** A cleaned post back as the same plain text, for changing it within the edit window. */
export function toText(html: string): string {
  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
  const walk = (node: Node): string => {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? "";
    if (!(node instanceof Element)) return "";
    const inner = Array.from(node.childNodes).map(walk).join("");
    switch (node.tagName.toLowerCase()) {
      case "strong":
      case "b":
        return `**${inner}**`;
      case "em":
      case "i":
        return `*${inner}*`;
      case "a": {
        const href = node.getAttribute("href") ?? "";
        return href === inner ? href : `[${inner}](${href})`;
      }
      case "br":
        return "\n";
      case "li":
        return `- ${inner.trim()}\n`;
      case "ul":
      case "ol":
        return `${inner}\n`;
      case "p":
      case "div":
      case "h2":
      case "h3":
      case "h4":
      case "blockquote":
      case "pre":
        return `${inner}\n\n`;
      default:
        return inner;
    }
  };
  return walk(doc.body)
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** Plain words of a cleaned body, for a one-line preview. */
export function preview(html: string, length = 120): string {
  const text = toText(html).replace(/\s+/g, " ").replace(/\*+/g, "");
  return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}
