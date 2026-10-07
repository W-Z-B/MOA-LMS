import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, errorMessage, get, patch, post, remove } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { Grouping, MyGroup, SiteGroup, SiteMember } from "../../api/types-talk";
import { dmyTime, plural } from "../../app/format";
import { fromLocalInput, localInput, rows } from "../forums/shared";
import "../talk.css";

const put = <T,>(path: string, data: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(data) });

interface Props {
  siteId: number;
  teaching: boolean;
}

/** A student's groups on the course and the self-sign-up groups they may join or leave (item 4.12). */
function MyGroups({ siteId }: { siteId: number }) {
  const [groups, setGroups] = useState<MyGroup[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    get<MyGroup[]>(`/sites/${siteId}/my-groups/`)
      .then(setGroups)
      .catch((err) => setError(errorMessage(err, "Could not load your groups.")));
  }, [siteId]);

  useEffect(load, [load]);

  async function change(group: MyGroup, joining: boolean) {
    try {
      await post(`/groups/${group.id}/${joining ? "join" : "leave"}/`);
      setNotice(joining ? `You joined ${group.name}.` : `You left ${group.name}.`);
      setError(null);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not change your group."));
    }
  }

  if (!groups) return error ? <p className="error">{error}</p> : <p className="loading">Loading groups…</p>;
  const mine = groups.filter((g) => g.member);
  const joinable = groups.filter((g) => !g.member && g.self_sign_up);

  const describe = (g: MyGroup) =>
    [
      g.groupings.join(", "),
      g.self_sign_up && (g.open ? "Sign-up open" : "Sign-up closed"),
      g.places_left !== null && plural(g.places_left, "place left", "places left"),
      g.closes_at && g.open && `closes ${dmyTime(g.closes_at)}`,
    ]
      .filter(Boolean)
      .join(" · ");

  return (
    <>
      {notice && (
        <p role="status" className="notice good">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <section aria-labelledby="my-groups">
        <h2 id="my-groups">My groups</h2>
        {mine.length === 0 ? (
          <p className="muted">You are not in a group on this course.</p>
        ) : (
          <ul className="talk-list" aria-label="My groups">
            {mine.map((g) => (
              <li key={g.id} className="talk-row">
                <span className="talk-row-main">
                  <span className="talk-title">{g.name}</span>
                  <span className="muted small">{describe(g)}</span>
                </span>
                {g.self_sign_up && g.open && (
                  <button className="secondary" onClick={() => change(g, false)}>
                    Leave
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      {joinable.length > 0 && (
        <section aria-labelledby="join-groups">
          <h2 id="join-groups">Groups you can join</h2>
          <p className="muted small">You may hold one group in each set. Join one while sign-up is open.</p>
          <ul className="talk-list" aria-label="Groups you can join">
            {joinable.map((g) => (
              <li key={g.id} className="talk-row">
                <span className="talk-row-main">
                  <span className="talk-title">{g.name}</span>
                  <span className="muted small">{describe(g)}</span>
                </span>
                <button disabled={!g.open || g.places_left === 0} onClick={() => change(g, true)} aria-label={`Join ${g.name}`}>
                  Join
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

/** Self-sign-up for one group: open or not, a largest size and a closing time. */
function SignUpEditor({ group, current, onDone }: { group: SiteGroup; current: MyGroup | undefined; onDone: (message: string) => void }) {
  const [open, setOpen] = useState(current?.open ?? true);
  // The largest size is what is left plus who is in it already.
  const [size, setSize] = useState(current?.places_left != null ? String(current.places_left + group.members.length) : "");
  const [closes, setCloses] = useState(localInput(current?.closes_at));
  const [error, setError] = useState<string | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      await put(`/groups/${group.id}/sign-up/`, { is_open: open, max_size: size ? Number(size) : null, closes_at: fromLocalInput(closes) });
      onDone(`Students can ${open ? "now join" : "no longer join"} ${group.name} themselves.`);
    } catch (err) {
      setError(errorMessage(err, "Could not change sign-up."));
    }
  }

  async function stop() {
    try {
      await remove(`/groups/${group.id}/sign-up/`);
      onDone(`Self-sign-up for ${group.name} is off; its members stay.`);
    } catch (err) {
      setError(errorMessage(err, "Could not stop sign-up."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={save}>
      <label className="inline">
        <input type="checkbox" checked={open} onChange={(e) => setOpen(e.target.checked)} />
        Students may join or leave {group.name} themselves
      </label>
      <div className="grid2">
        <label>
          Largest size (empty: no limit)
          <input type="number" min="1" value={size} onChange={(e) => setSize(e.target.value)} />
        </label>
        <label>
          Sign-up closes (optional)
          <input type="datetime-local" value={closes} onChange={(e) => setCloses(e.target.value)} />
        </label>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit">Save sign-up</button>
        {current?.self_sign_up && (
          <button type="button" className="secondary" onClick={stop}>
            Stop self-sign-up
          </button>
        )}
      </div>
    </form>
  );
}

/** Teaching staff: groups by hand, at random, groupings, and self-sign-up (item 4.12). */
function ManageGroups({ siteId }: { siteId: number }) {
  const [groups, setGroups] = useState<SiteGroup[]>([]);
  const [info, setInfo] = useState<MyGroup[]>([]);
  const [groupings, setGroupings] = useState<Grouping[]>([]);
  const [students, setStudents] = useState<SiteMember[]>([]);
  const [editing, setEditing] = useState<{ id: number | null; name: string; members: number[] } | null>(null);
  const [signUp, setSignUp] = useState<number | null>(null);
  const [random, setRandom] = useState<{ by: "groups" | "size"; n: string; prefix: string; grouping: string } | null>(null);
  const [newGrouping, setNewGrouping] = useState<{ name: string; groups: number[] } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([
      get<Paginated<SiteGroup> | SiteGroup[]>(`/groups/?site=${siteId}`),
      get<MyGroup[]>(`/sites/${siteId}/my-groups/`),
      get<Paginated<Grouping> | Grouping[]>(`/groupings/?site=${siteId}`),
      get<SiteMember[]>(`/sites/${siteId}/members/`),
    ])
      .then(([g, i, gs, m]) => {
        setGroups(rows(g));
        setInfo(i);
        setGroupings(rows(gs));
        setStudents(m.filter((member) => member.role === "student"));
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load the groups.")));
  }, [siteId]);

  useEffect(load, [load]);

  const done = (message: string) => {
    setNotice(message);
    setError(null);
    setEditing(null);
    setSignUp(null);
    setRandom(null);
    setNewGrouping(null);
    load();
  };
  const name = (membership: number) => students.find((s) => s.membership_id === membership)?.name ?? "A former member";

  async function saveGroup(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    try {
      if (editing.id === null) await post("/groups/", { site: siteId, name: editing.name, members: editing.members });
      else await patch(`/groups/${editing.id}/`, { name: editing.name, members: editing.members });
      done(`${editing.name} is saved with ${plural(editing.members.length, "member", "members")}.`);
    } catch (err) {
      setError(errorMessage(err, "Could not save the group."));
    }
  }

  async function allocate(e: FormEvent) {
    e.preventDefault();
    if (!random) return;
    try {
      const answer = await post<{ groups: { name: string }[] }>(`/sites/${siteId}/allocate-groups/`, {
        [random.by]: Number(random.n),
        prefix: random.prefix,
        grouping: random.grouping,
      });
      done(`${plural(answer.groups.length, "group", "groups")} made at random.`);
    } catch (err) {
      setError(errorMessage(err, "Could not share the students into groups."));
    }
  }

  async function saveGrouping(e: FormEvent) {
    e.preventDefault();
    if (!newGrouping) return;
    try {
      await post("/groupings/", { site: siteId, name: newGrouping.name, groups: newGrouping.groups });
      done(`The set ${newGrouping.name} is saved.`);
    } catch (err) {
      setError(errorMessage(err, "Could not save the set of groups."));
    }
  }

  const toggle = (list: number[], id: number) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

  return (
    <>
      {notice && (
        <p role="status" className="notice good">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <h2>Groups</h2>
      {groups.length === 0 && <p className="muted">No groups yet. Make them by hand or share the students at random.</p>}
      <ul className="talk-list" aria-label="Groups">
        {groups.map((g) => {
          const about = info.find((i) => i.id === g.id);
          return (
            <li key={g.id} className="group-row">
              <div className="spread">
                <span className="talk-row-main">
                  <span className="talk-title">{g.name}</span>
                  <span className="muted small">
                    {plural(g.members.length, "member", "members")}
                    {about?.groupings.length ? ` · ${about.groupings.join(", ")}` : ""}
                    {about?.self_sign_up ? (about.open ? " · Self-sign-up open" : " · Self-sign-up closed") : ""}
                  </span>
                  {g.members.length > 0 && <span className="small">{g.members.map(name).join(", ")}</span>}
                </span>
                <div className="actions">
                  <button className="secondary" onClick={() => setEditing({ id: g.id, name: g.name, members: g.members })} aria-label={`Change ${g.name}`}>
                    Change
                  </button>
                  <button className="secondary" onClick={() => setSignUp(signUp === g.id ? null : g.id)} aria-label={`Sign-up for ${g.name}`}>
                    Sign-up
                  </button>
                </div>
              </div>
              {signUp === g.id && <SignUpEditor group={g} current={about} onDone={done} />}
            </li>
          );
        })}
      </ul>

      {editing && (
        <form className="stack module" onSubmit={saveGroup}>
          <h3>{editing.id === null ? "New group" : `Change ${editing.name}`}</h3>
          <label>
            Name
            <input required maxLength={80} value={editing.name} onChange={(e) => setEditing((prev) => prev && ({ ...prev, name: e.target.value }))} />
          </label>
          <fieldset>
            <legend>Students in it</legend>
            <div className="talk-choices">
              {students.map((s) => (
                <label key={s.membership_id} className="inline">
                  <input
                    type="checkbox"
                    checked={editing.members.includes(s.membership_id)}
                    onChange={() => setEditing((prev) => prev && ({ ...prev, members: toggle(editing.members, s.membership_id) }))}
                  />
                  {s.name} <span className="muted small">{s.external_id}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
            <button type="submit">Save group</button>
          </div>
        </form>
      )}

      {random && (
        <form className="stack module" onSubmit={allocate}>
          <h3>Share the students at random</h3>
          <p className="muted small">New groups are made; the groups there already stay as they are.</p>
          <fieldset>
            <legend>How</legend>
            <label className="inline">
              <input type="radio" name="by" checked={random.by === "groups"} onChange={() => setRandom((prev) => prev && ({ ...prev, by: "groups" }))} />
              This many groups
            </label>
            <label className="inline">
              <input type="radio" name="by" checked={random.by === "size"} onChange={() => setRandom((prev) => prev && ({ ...prev, by: "size" }))} />
              Groups of at most this many
            </label>
          </fieldset>
          <div className="grid2">
            <label>
              {random.by === "groups" ? "Number of groups" : "Students in a group"}
              <input required type="number" min="1" value={random.n} onChange={(e) => setRandom((prev) => prev && ({ ...prev, n: e.target.value }))} />
            </label>
            <label>
              Name the groups
              <input value={random.prefix} maxLength={60} onChange={(e) => setRandom((prev) => prev && ({ ...prev, prefix: e.target.value }))} />
            </label>
            <label className="span2">
              Put them in a new set (optional), such as “Lab groups”
              <input value={random.grouping} maxLength={80} onChange={(e) => setRandom((prev) => prev && ({ ...prev, grouping: e.target.value }))} />
            </label>
          </div>
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setRandom(null)}>
              Cancel
            </button>
            <button type="submit">Make the groups</button>
          </div>
        </form>
      )}

      {newGrouping && (
        <form className="stack module" onSubmit={saveGrouping}>
          <h3>New set of groups</h3>
          <label>
            Name, such as “Field groups”
            <input required maxLength={80} value={newGrouping.name} onChange={(e) => setNewGrouping((prev) => prev && ({ ...prev, name: e.target.value }))} />
          </label>
          <fieldset>
            <legend>Groups in the set</legend>
            <div className="talk-choices">
              {groups.map((g) => (
                <label key={g.id} className="inline">
                  <input type="checkbox" checked={newGrouping.groups.includes(g.id)} onChange={() => setNewGrouping((prev) => prev && ({ ...prev, groups: toggle(newGrouping.groups, g.id) }))} />
                  {g.name}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setNewGrouping(null)}>
              Cancel
            </button>
            <button type="submit">Save set</button>
          </div>
        </form>
      )}

      {!editing && !random && !newGrouping && (
        <div className="actions talk-foot">
          <button onClick={() => setEditing({ id: null, name: "", members: [] })}>New group</button>
          <button className="secondary" onClick={() => setRandom({ by: "groups", n: "4", prefix: "Group", grouping: "" })}>
            Share students at random
          </button>
          <button className="secondary" onClick={() => setNewGrouping({ name: "", groups: [] })}>
            New set of groups
          </button>
        </div>
      )}

      {groupings.length > 0 && (
        <section aria-labelledby="groupings-title">
          <h2 id="groupings-title">Sets of groups</h2>
          <ul className="plain">
            {groupings.map((gs) => (
              <li key={gs.id}>
                <strong>{gs.name}</strong>{" "}
                <span className="muted small">{gs.groups.map((id) => groups.find((g) => g.id === id)?.name).filter(Boolean).join(", ") || "No groups yet"}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

/** A course site's Groups tab: teaching staff manage the groups; students see theirs and sign up. */
export function GroupsTab({ siteId, teaching }: Props) {
  return teaching ? <ManageGroups siteId={siteId} /> : <MyGroups siteId={siteId} />;
}
