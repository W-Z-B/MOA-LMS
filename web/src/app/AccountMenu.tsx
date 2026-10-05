import type { ReactNode } from "react";
import type { Me } from "../api/types";
import { initials } from "./format";
import { roleTitle } from "./people";
import { Popover } from "./Popover";

interface Props {
  me: Me;
  open: boolean;
  phone: boolean;
  onToggle: () => void;
  onClose: () => void;
  onNavigate: (to: string) => void;
  onSignOut: () => void;
  /** On a phone the campus switch lives here, as the header has no room for it. */
  campusSwitch?: ReactNode;
}

const MINE = [
  { path: "/courses", label: "My courses", desc: "Your course sites" },
  { path: "/my-data", label: "My data", desc: "What the LMS holds about you" },
  { path: "/account", label: "My account", desc: "Authenticator and signed-in devices" },
  { path: "/notification-settings", label: "Notification settings", desc: "What comes by email" },
];

/** The person's own pages and Sign out, behind their initials (as in the HRMS). */
export function AccountMenu({ me, open, phone, onToggle, onClose, onNavigate, onSignOut, campusSwitch }: Props) {
  return (
    <div className="account">
      <button className="avatar-button" aria-expanded={open} aria-label={`Signed in as ${me.name}`} onClick={onToggle}>
        <span className="avatar">{initials(me.name)}</span>
      </button>
      {open && (
        <Popover label="Your account" phone={phone} onClose={onClose}>
          <div className="popover-head stacked">
            <strong>{me.name}</strong>
            <span className="muted small">{roleTitle(me)}</span>
          </div>
          {campusSwitch}
          <ul className="menu-list">
            {MINE.map((item) => (
              <li key={item.path}>
                <a
                  href={`#${item.path}`}
                  onClick={(e) => {
                    e.preventDefault();
                    onClose();
                    onNavigate(item.path);
                  }}
                >
                  <span className="menu-label">{item.label}</span>
                  <span className="muted small">{item.desc}</span>
                </a>
              </li>
            ))}
          </ul>
          <div className="popover-foot">
            <button className="secondary" onClick={onSignOut}>
              Sign out
            </button>
          </div>
        </Popover>
      )}
    </div>
  );
}
