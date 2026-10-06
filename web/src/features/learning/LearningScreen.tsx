import { hasAnyRole, type Me } from "../../api/types";
import { OVERSEERS, usesLearning } from "../../api/types-staff";
import { NavTabs } from "../admin/kit";
import { learningAddress } from "./address";
import { Approvals } from "./Approvals";
import { Catalogue, CoursePage } from "./Catalogue";
import { Certificates } from "./Certificates";
import { MyLearning } from "./MyLearning";
import { Paths } from "./Paths";
import { RequiredTraining } from "./RequiredTraining";
import { Templates } from "./Templates";

interface Props {
  me: Me;
  path: string;
  onNavigate: (to: string) => void;
}

/**
 * Staff development (items 5.02 to 5.11, features 35 to 38): the catalogue and each course, my learning,
 * learning paths, certificates, decisions on requests to join and stand-ins; for course administrators and
 * the auditor also required training and certificate templates.
 */
export function LearningScreen({ me, path, onNavigate }: Props) {
  const address = learningAddress(path) ?? { tab: "catalogue" as const, id: null };
  if (!usesLearning(me))
    return (
      <>
        <h1>Staff development</h1>
        <p className="muted">Staff-development courses are for members of staff.</p>
      </>
    );
  const overseer = hasAnyRole(me, OVERSEERS);
  const tabs = [
    { to: "/learning", label: "Catalogue" },
    { to: "/learning/mine", label: "My learning" },
    { to: "/learning/paths", label: "Learning paths" },
    { to: "/learning/certificates", label: "Certificates" },
    { to: "/learning/approvals", label: "Approvals" },
    ...(overseer
      ? [
          { to: "/learning/required", label: "Required training" },
          { to: "/learning/templates", label: "Certificate templates" },
        ]
      : []),
  ];
  const current = {
    catalogue: "/learning",
    course: "/learning",
    mine: "/learning/mine",
    paths: "/learning/paths",
    certificates: "/learning/certificates",
    approvals: "/learning/approvals",
    required: "/learning/required",
    templates: "/learning/templates",
  }[address.tab];

  let body;
  if (address.tab === "course" && address.id !== null) body = <CoursePage site={address.id} onNavigate={onNavigate} />;
  else if (address.tab === "mine") body = <MyLearning onNavigate={onNavigate} />;
  else if (address.tab === "paths") body = <Paths id={address.id} onNavigate={onNavigate} />;
  else if (address.tab === "certificates") body = <Certificates me={me} />;
  else if (address.tab === "approvals") body = <Approvals me={me} highlight={address.id} />;
  else if (address.tab === "required" && overseer) body = <RequiredTraining me={me} />;
  else if (address.tab === "templates" && overseer) body = <Templates me={me} />;
  else body = <Catalogue onNavigate={onNavigate} />;

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>Staff development</h1>
          <p className="muted lead">Courses for members of staff, the paths through them, and the certificates they earn.</p>
        </div>
      </div>
      <NavTabs label="Staff development" tabs={tabs} current={current} onNavigate={onNavigate} />
      {body}
    </>
  );
}
