import { pageOf } from "./router";

interface Props {
  path: string;
  /** The item open on the page, if the page has named one. */
  item: string | null;
  onNavigate: (to: string) => void;
}

/** Home / My courses / Introduction to Crop Production: every page but Home shows the way back (item 2.10). */
export function Breadcrumbs({ path, item, onNavigate }: Props) {
  const page = pageOf(path);
  if (path === "/" || !page) return null;
  const trail = [
    { label: "Home", to: "/" },
    { label: page.label, to: item ? page.path : null },
    ...(item ? [{ label: item, to: null }] : []),
  ];
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      <ol>
        {trail.map((crumb, at) => (
          <li key={at}>
            {crumb.to !== null ? (
              <a
                href={`#${crumb.to}`}
                onClick={(e) => {
                  e.preventDefault();
                  onNavigate(crumb.to!);
                }}
              >
                {crumb.label}
              </a>
            ) : (
              <span aria-current="page">{crumb.label}</span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
