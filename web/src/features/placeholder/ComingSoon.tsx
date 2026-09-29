interface Props {
  title: string;
  sprint: string;
  requirement: string;
}

/** Placeholder screen for modules scheduled in later sprints. */
export function ComingSoon({ title, sprint, requirement }: Props) {
  return (
    <>
      <h1>{title}</h1>
      <p className="muted">
        This module ({requirement}) is scheduled for {sprint}. The API scaffold already exists; the screens follow the
        wireframes in the project documents.
      </p>
    </>
  );
}
