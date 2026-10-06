import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { Platform, Tool } from "../../api/types-connect";
import { useCrumb } from "../../app/frame";
import "./tools.css";

type Form = {
  name: string;
  description: string;
  oidc_login_url: string;
  launch_url: string;
  deep_linking_url: string;
  jwks_url: string;
  public_key: string;
};

const EMPTY: Form = { name: "", description: "", oidc_login_url: "", launch_url: "", deep_linking_url: "", jwks_url: "", public_key: "" };

/**
 * Outside tools (item 6.07), for course administrators: the LMS's details to give a tool's maker, the tools
 * registered, and for each what it may do and what it receives. Names and email addresses are each off
 * until switched on for a tool; the impact assessment says what to record first (DPIA section 7a).
 */
export default function ToolsAdminScreen() {
  const [tools, setTools] = useState<Tool[] | null>(null);
  const [platform, setPlatform] = useState<Platform | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  useCrumb("Outside tools");

  const load = () =>
    get<Paginated<Tool>>("/tools/")
      .then((page) => setTools(page.results))
      .catch((err) => setError(errorMessage(err, "Could not read the tools.")));

  useEffect(() => {
    load();
    get<Platform>("/lti/platform/")
      .then(setPlatform)
      .catch(() => setPlatform(null));
  }, []);

  return (
    <div className="tools">
      <div className="page-head">
        <h1>Outside tools</h1>
        {!adding && (
          <button type="button" onClick={() => setAdding(true)}>
            Register a tool
          </button>
        )}
      </div>
      <p className="muted">
        Tools courses can open without a second sign-in (LTI 1.3). A tool receives a code for each person, their role and the course;
        names and email addresses only where you switch them on for that tool.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {adding && (
        <ToolForm
          onCancel={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            void load();
          }}
        />
      )}
      {tools === null && !error && <p className="loading">Reading the tools…</p>}
      {tools?.length === 0 && <p className="muted">No tools are registered yet.</p>}
      <ul className="plain tool-list" aria-label="Registered tools">
        {(tools ?? []).map((tool) => (
          <ToolCard key={tool.id} tool={tool} onChanged={(changed) => setTools((all) => all?.map((t) => (t.id === changed.id ? changed : t)) ?? null)} />
        ))}
      </ul>
      {platform && (
        <section aria-labelledby="platform-details" className="panel-card padded">
          <h2 id="platform-details">The LMS's details, for a tool's maker</h2>
          <dl className="tool-details">
            <dt>Issuer (platform ID)</dt>
            <dd>{platform.issuer}</dd>
            <dt>Public keyset URL</dt>
            <dd>{platform.jwks_url}</dd>
            <dt>OIDC authorisation URL</dt>
            <dd>{platform.auth_url}</dd>
            <dt>Access token URL</dt>
            <dd>{platform.token_url}</dd>
            <dt>Deep linking return URL</dt>
            <dd>{platform.deep_link_return_url}</dd>
          </dl>
        </section>
      )}
    </div>
  );
}

function ToolCard({ tool, onChanged }: { tool: Tool; onChanged: (tool: Tool) => void }) {
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  async function set(change: Partial<Tool>, said: string) {
    try {
      onChanged(await patch<Tool>(`/tools/${tool.id}/`, change));
      setMessage({ ok: true, text: said });
    } catch (err) {
      setMessage({ ok: false, text: errorMessage(err, "Could not change the tool.") });
    }
  }
  const toggle = (name: "share_name" | "share_email" | "grades" | "class_list" | "is_active", label: string) => (
    <label className="inline">
      <input type="checkbox" checked={tool[name]} onChange={(e) => set({ [name]: e.target.checked }, `${label}: ${e.target.checked ? "on" : "off"}.`)} /> {label}
    </label>
  );
  return (
    <li className="panel-card padded">
      <h2 className="item-title">
        {tool.name}
        {!tool.is_active && <span className="badge">Switched off</span>}
      </h2>
      {tool.description && <p>{tool.description}</p>}
      <dl className="tool-details small">
        <dt>Client ID</dt>
        <dd>{tool.client_id}</dd>
        <dt>Deployment ID</dt>
        <dd>{tool.deployment_id}</dd>
        <dt>Login initiation</dt>
        <dd>{tool.oidc_login_url}</dd>
        <dt>Launch</dt>
        <dd>{tool.launch_url}</dd>
        {tool.deep_linking_url && (
          <>
            <dt>Content selection</dt>
            <dd>{tool.deep_linking_url}</dd>
          </>
        )}
        <dt>Key</dt>
        <dd>{tool.jwks_url || "Public key pasted in"}</dd>
      </dl>
      <fieldset className="stack">
        <legend>What the tool may know and do</legend>
        {toggle("share_name", "Send people's names")}
        {toggle("share_email", "Send people's email addresses")}
        {toggle("grades", "Post scores to the gradebook")}
        {toggle("class_list", "Read class lists")}
        {toggle("is_active", "Switched on")}
      </fieldset>
      <div className="notice receives">
        <p>
          <strong>It receives</strong>
        </p>
        <ul>
          {tool.receives.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </div>
      {message && (
        <p role={message.ok ? "status" : "alert"} className={message.ok ? "muted small" : "error"}>
          {message.text}
        </p>
      )}
    </li>
  );
}

function ToolForm({ onCancel, onSaved }: { onCancel: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<Form>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const set = (name: keyof Form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [name]: e.target.value }));

  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      await post<Tool>("/tools/", form);
      onSaved();
    } catch (err) {
      setError(errorMessage(err, "Could not register the tool."));
    }
  }

  return (
    <form className="stack sub-form panel-card padded" onSubmit={save} aria-label="Register a tool">
      <label>
        Name
        <input value={form.name} onChange={set("name")} required maxLength={120} />
      </label>
      <label>
        What it is for
        <textarea value={form.description} onChange={set("description")} />
      </label>
      <label>
        Login initiation address (OIDC login)
        <input type="url" value={form.oidc_login_url} onChange={set("oidc_login_url")} required placeholder="https://" />
      </label>
      <label>
        Launch address (target link)
        <input type="url" value={form.launch_url} onChange={set("launch_url")} required placeholder="https://" />
      </label>
      <label>
        Content selection address (deep linking), if it has one
        <input type="url" value={form.deep_linking_url} onChange={set("deep_linking_url")} placeholder="https://" />
      </label>
      <label>
        Key set address (JWKS URL)
        <input type="url" value={form.jwks_url} onChange={set("jwks_url")} placeholder="https://" />
      </label>
      <label>
        Or its public key (PEM or JWK)
        <textarea value={form.public_key} onChange={set("public_key")} />
      </label>
      <p className="muted small">Names and email addresses are not sent until you switch them on for this tool.</p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit">Register</button>
      </div>
    </form>
  );
}
