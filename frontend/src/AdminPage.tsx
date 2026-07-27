import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BarChart3,
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  Download,
  ExternalLink,
  KeyRound,
  Menu,
  Plus,
  QrCode,
  RefreshCw,
  Search,
  ShieldCheck,
  UserCog,
  Users,
  X,
} from "lucide-react";

import {
  api,
  Checkin,
  formatMeetingDate,
  Meeting,
  MeetingStatus,
  Profile,
  setCsrfToken,
} from "./api";
import { Brand, Button, EmptyState, Field, StatusBadge } from "./components";

interface Me {
  id: string;
  display_name: string;
  email: string;
  role: string;
  csrf_token: string;
}

export function AdminPage() {
  const [menuOpen, setMenuOpen] = useState(false);
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/api/v1/auth/me"), retry: false });
  useEffect(() => {
    setCsrfToken(me.data?.csrf_token ?? null);
  }, [me.data?.csrf_token]);

  if (me.isLoading) return <div className="app-loading">Loading organizer workspace…</div>;
  const organizer = me.data;
  if (me.isError || !organizer) {
    return <OrganizerLogin onSignedIn={() => me.refetch()} />;
  }

  return (
    <div className="admin-shell">
      <aside className={menuOpen ? "sidebar sidebar--open" : "sidebar"}>
        <div className="sidebar__head">
          <Brand compact />
          <button className="icon-button sidebar__close" onClick={() => setMenuOpen(false)}><X /></button>
        </div>
        <nav onClick={() => setMenuOpen(false)}>
          <a href="/admin" className={window.location.pathname === "/admin" ? "active" : ""}><BarChart3 />Overview</a>
          <a href="/admin/meetings" className={window.location.pathname === "/admin/meetings" ? "active" : ""}><CalendarDays />Meetings</a>
          <a href="/admin/profiles" className={window.location.pathname === "/admin/profiles" ? "active" : ""}><Users />Profiles</a>
          {organizer.role === "owner" && (
            <a href="/admin/organizers" className={window.location.pathname === "/admin/organizers" ? "active" : ""}><UserCog />Organizers</a>
          )}
          <a href="/admin/security" className={window.location.pathname === "/admin/security" ? "active" : ""}><KeyRound />My password</a>
        </nav>
        <div className="sidebar__user">
          <div>{organizer.display_name.charAt(0)}</div>
          <span><strong>{organizer.display_name}</strong><small>{organizer.role}</small></span>
        </div>
      </aside>
      <div className="admin-main">
        <header className="admin-topbar">
          <button className="icon-button mobile-menu" onClick={() => setMenuOpen(true)}><Menu /></button>
          <div><span>Organizer workspace</span><strong>Phoenixville Democrats</strong></div>
          <button
            className="text-button"
            onClick={async () => {
              await api("/api/v1/auth/logout", { method: "POST" });
              setCsrfToken(null);
              window.location.assign("/");
            }}
          >
            Sign out
          </button>
        </header>
        {window.location.pathname === "/admin/organizers" && organizer.role === "owner" ? (
          <Organizers currentId={organizer.id} />
        ) : window.location.pathname === "/admin/security" ? (
          <AccountSecurity />
        ) : window.location.pathname === "/admin/meetings" ? (
          <Meetings />
        ) : window.location.pathname === "/admin/profiles" ? (
          <Profiles />
        ) : (
          <Overview />
        )}
      </div>
    </div>
  );
}

function OrganizerLogin({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () =>
      api<{ signed_in: boolean; csrf_token: string }>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      }),
    onSuccess(data) {
      setCsrfToken(data.csrf_token);
      onSignedIn();
    },
  });

  return (
    <div className="login-page">
      <Brand />
      <div className="login-card">
        <div className="welcome-orb">P</div>
        <div className="eyebrow">Committee access</div>
        <h1>Organizer workspace</h1>
        <p>Sign in to manage meetings, check-ins, and attendee records.</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            login.mutate();
          }}
        >
          <Field
            label="Email"
            name="email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
          <Field
            label="Password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          {login.isError && (
            <div className="form-error" role="alert">{login.error.message}</div>
          )}
          <Button type="submit" busy={login.isPending} className="button--wide">
            Sign in
          </Button>
        </form>
        <a className="text-button" href="/">Back to check-in</a>
      </div>
    </div>
  );
}

function Overview() {
  const data = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<{ counts: Record<string, number>; recent_meetings: Meeting[] }>("/api/v1/admin/dashboard"),
  });
  if (!data.data) return <PageLoading />;
  return (
    <main className="admin-content">
      <PageTitle eyebrow="At a glance" title="Good to see you." subtitle="Monthly meeting attendance, without the clipboard." />
      <section className="stat-grid">
        <Stat icon={<Users />} value={data.data.counts.profiles} label="Profiles" accent="blue" />
        <Stat icon={<ClipboardCheck />} value={data.data.counts.checkins} label="Total check-ins" accent="red" />
        <Stat icon={<CalendarDays />} value={data.data.counts.meetings} label="Meetings" accent="gold" />
      </section>
      <section className="panel">
        <div className="panel__head"><div><span className="eyebrow">Recent activity</span><h2>Meetings</h2></div><a className="text-link" href="/admin/meetings">View all <ExternalLink size={15} /></a></div>
        {data.data.recent_meetings.length ? (
          <div className="meeting-list">
            {data.data.recent_meetings.map((meeting) => <MeetingRow key={meeting.id} meeting={meeting} />)}
          </div>
        ) : (
          <EmptyState icon={<CalendarDays />} title="No meetings yet">Create your first monthly meeting to generate a check-in link.</EmptyState>
        )}
      </section>
    </main>
  );
}

function Meetings() {
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<Meeting | null>(null);
  const meetings = useQuery({ queryKey: ["meetings"], queryFn: () => api<Meeting[]>("/api/v1/admin/meetings") });
  const create = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const data = new FormData(form);
      return api<Meeting>("/api/v1/admin/meetings", {
        method: "POST",
        body: JSON.stringify({
          title: data.get("title"),
          starts_at: new Date(String(data.get("starts_at"))).toISOString(),
          location: data.get("location") || null,
          attendee_message: data.get("attendee_message") || null,
        }),
      });
    },
    onSuccess(meeting) {
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      setCreating(false);
      setSelected(meeting);
    },
  });

  return (
    <main className="admin-content">
      <div className="title-action">
        <PageTitle eyebrow="Attendance" title="Meetings" subtitle="Create a meeting, open its check-in, and share the QR code." />
        <Button onClick={() => setCreating(true)}><Plus size={18} />New meeting</Button>
      </div>
      <section className="panel">
        {meetings.data?.length ? (
          <div className="meeting-list">
            {meetings.data.map((meeting) => (
              <button className="meeting-row meeting-row--button" key={meeting.id} onClick={() => setSelected(meeting)}>
                <MeetingRowContent meeting={meeting} />
              </button>
            ))}
          </div>
        ) : <EmptyState icon={<CalendarDays />} title="Your first meeting starts here">Create a meeting and we’ll make its shareable QR code.</EmptyState>}
      </section>

      {creating && (
        <Modal title="Create a meeting" onClose={() => setCreating(false)}>
          <form className="modal-form" onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); create.mutate(event.currentTarget); }}>
            <Field label="Meeting title" name="title" placeholder="August monthly meeting" required autoFocus />
            <Field label="Date and time" name="starts_at" type="datetime-local" required />
            <Field label="Location (optional)" name="location" placeholder="Phoenixville Recreation Center" />
            <label className="field">
              <span>Welcome message (optional)</span>
              <textarea name="attendee_message" rows={3} placeholder="Thanks for joining us…" />
            </label>
            {create.isError && <div className="form-error">{create.error.message}</div>}
            <div className="modal-actions"><Button variant="secondary" type="button" onClick={() => setCreating(false)}>Cancel</Button><Button busy={create.isPending}>Create meeting</Button></div>
          </form>
        </Modal>
      )}
      {selected && <MeetingDrawer meeting={selected} onClose={() => setSelected(null)} />}
    </main>
  );
}

function MeetingDrawer({ meeting, onClose }: { meeting: Meeting; onClose: () => void }) {
  const queryClient = useQueryClient();
  const attendance = useQuery({
    queryKey: ["meeting-checkins", meeting.id],
    queryFn: () => api<{ meeting: Meeting; checkins: Checkin[] }>(`/api/v1/admin/meetings/${meeting.id}/checkins`),
    refetchInterval: meeting.status === "open" ? 5000 : false,
  });
  const status = useMutation({
    mutationFn: (next: MeetingStatus) =>
      api<Meeting>(`/api/v1/admin/meetings/${meeting.id}/status`, { method: "PATCH", body: JSON.stringify({ status: next }) }),
    onSuccess() {
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onClose();
    },
  });
  const link = `${window.location.origin}/checkin/${meeting.public_token}`;
  return (
    <div className="drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="drawer">
        <div className="drawer__head"><div><StatusBadge status={meeting.status} /><h2>{meeting.title}</h2><p>{formatMeetingDate(meeting.starts_at)}</p></div><button className="icon-button" onClick={onClose}><X /></button></div>
        <div className="drawer__actions">
          {meeting.status !== "open" ? <Button onClick={() => status.mutate("open")} busy={status.isPending}><CheckCircle2 size={17} />Open check-in</Button> : <Button variant="secondary" onClick={() => status.mutate("closed")} busy={status.isPending}>Close check-in</Button>}
          <a className="button button--secondary" href={`/api/v1/admin/meetings/${meeting.id}/qr.svg`}><QrCode size={17} />QR code</a>
          <a className="button button--quiet" href={`/api/v1/admin/meetings/${meeting.id}/export.csv`}><Download size={17} />CSV</a>
        </div>
        <div className="share-box">
          <label>Public check-in link</label>
          <div><code>{link}</code><Button variant="quiet" onClick={() => navigator.clipboard.writeText(link)}>Copy</Button></div>
        </div>
        <div className="drawer__section-title"><span>Attendance</span><strong>{attendance.data?.checkins.length ?? 0}</strong></div>
        <div className="attendance-list">
          {attendance.data?.checkins.map((item) => (
            <div key={item.id} className="attendance-row">
              <div className="avatar">{item.profile?.first_name.charAt(0) ?? "—"}</div>
              <span><strong>{item.profile ? `${item.profile.first_name} ${item.profile.last_name}` : item.anonymized_name}</strong><small>{new Date(item.checked_in_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} · {item.source}</small></span>
              <CheckCircle2 size={19} />
            </div>
          ))}
          {!attendance.data?.checkins.length && <EmptyState icon={<ClipboardCheck />} title="No check-ins yet">Open and share the meeting link to begin.</EmptyState>}
        </div>
      </aside>
    </div>
  );
}

function Profiles() {
  const [search, setSearch] = useState("");
  const profiles = useQuery({
    queryKey: ["profiles", search],
    queryFn: () => api<Profile[]>(`/api/v1/admin/profiles?q=${encodeURIComponent(search)}`),
  });
  return (
    <main className="admin-content">
      <PageTitle eyebrow="Community" title="Profiles" subtitle="Find people and review the contact information they shared." />
      <section className="panel">
        <div className="search-box"><Search size={19} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by name or email…" aria-label="Search profiles" /></div>
        <div className="profile-table">
          <div className="profile-table__header"><span>Name</span><span>Email</span><span>Phone</span><span>Joined</span></div>
          {profiles.data?.map((profile) => (
            <div className="profile-table__row" key={profile.id}>
              <span><div className="avatar">{profile.first_name.charAt(0)}</div><strong>{profile.first_name} {profile.last_name}</strong></span>
              <span>{profile.email}</span><span>{profile.phone || "—"}</span>
              <span>{new Date(profile.created_at).toLocaleDateString()}</span>
            </div>
          ))}
        </div>
        {!profiles.data?.length && <EmptyState icon={<Users />} title="No profiles found">Profiles appear when attendees first check in.</EmptyState>}
      </section>
    </main>
  );
}

interface OrganizerAccount {
  id: string;
  email: string;
  display_name: string;
  role: "owner" | "admin";
  active: boolean;
  password_set: boolean;
  created_at: string;
  last_login_at: string | null;
}

interface AuthActivity {
  id: string;
  actor_id: string | null;
  action: string;
  created_at: string;
}

function Organizers({ currentId }: { currentId: string }) {
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [setupUrl, setSetupUrl] = useState("");
  const organizers = useQuery({
    queryKey: ["organizers"],
    queryFn: () => api<OrganizerAccount[]>("/api/v1/admin/organizers"),
  });
  const activity = useQuery({
    queryKey: ["organizer-activity"],
    queryFn: () => api<AuthActivity[]>("/api/v1/admin/organizers/activity"),
  });
  const create = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const data = new FormData(form);
      return api<OrganizerAccount & { setup_url: string }>("/api/v1/admin/organizers", {
        method: "POST",
        body: JSON.stringify({
          display_name: data.get("display_name"),
          email: data.get("email"),
          role: data.get("role"),
        }),
      });
    },
    onSuccess(data) {
      queryClient.invalidateQueries({ queryKey: ["organizers"] });
      setCreating(false);
      setSetupUrl(data.setup_url);
    },
  });
  const update = useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: Partial<OrganizerAccount> }) =>
      api<OrganizerAccount>(`/api/v1/admin/organizers/${id}`, {
        method: "PATCH",
        body: JSON.stringify(changes),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["organizers"] }),
  });
  const setupLink = useMutation({
    mutationFn: (id: string) =>
      api<{ setup_url: string }>(`/api/v1/admin/organizers/${id}/setup-link`, {
        method: "POST",
      }),
    onSuccess(data) {
      setSetupUrl(data.setup_url);
      queryClient.invalidateQueries({ queryKey: ["organizer-activity"] });
    },
  });
  const organizerById = new Map(organizers.data?.map((item) => [item.id, item]));

  return (
    <main className="admin-content">
      <div className="title-action">
        <PageTitle eyebrow="Access control" title="Organizers" subtitle="Provision accounts without sharing passwords." />
        <Button onClick={() => setCreating(true)}><Plus size={18} />New organizer</Button>
      </div>
      <section className="panel">
        <div className="organizer-table">
          <div className="organizer-table__header"><span>Organizer</span><span>Role</span><span>Last sign-in</span><span>Account</span><span>Actions</span></div>
          {organizers.data?.map((item) => (
            <div className="organizer-table__row" key={item.id}>
              <span><div className="avatar">{item.display_name.charAt(0)}</div><span><strong>{item.display_name}</strong><small>{item.email}</small></span></span>
              <select
                aria-label={`Role for ${item.display_name}`}
                value={item.role}
                disabled={item.id === currentId || update.isPending}
                onChange={(event) => update.mutate({ id: item.id, changes: { role: event.target.value as "owner" | "admin" } })}
              >
                <option value="admin">Admin</option>
                <option value="owner">Owner</option>
              </select>
              <span>{item.last_login_at ? new Date(item.last_login_at).toLocaleString() : "Never"}</span>
              <span className={`status status--${item.active ? "open" : "closed"}`}>{item.active ? (item.password_set ? "Active" : "Setup pending") : "Inactive"}</span>
              <span className="organizer-actions">
                <Button variant="quiet" onClick={() => setupLink.mutate(item.id)} busy={setupLink.isPending}><RefreshCw size={15} />Setup link</Button>
                {item.id !== currentId && (
                  <Button
                    variant={item.active ? "danger" : "secondary"}
                    onClick={() => update.mutate({ id: item.id, changes: { active: !item.active } })}
                    busy={update.isPending}
                  >
                    {item.active ? "Deactivate" : "Reactivate"}
                  </Button>
                )}
              </span>
            </div>
          ))}
        </div>
      </section>
      <section className="panel">
        <div className="panel__head"><div><span className="eyebrow">Security log</span><h2>Recent account activity</h2></div></div>
        <div className="activity-list">
          {activity.data?.map((event) => {
            const actor = event.actor_id ? organizerById.get(event.actor_id) : null;
            return <div key={event.id}><ShieldCheck size={18} /><span><strong>{event.action.replace("auth.", "").replaceAll("_", " ")}</strong><small>{actor?.display_name ?? "Unrecognized sign-in"} · {new Date(event.created_at).toLocaleString()}</small></span></div>;
          })}
          {!activity.data?.length && <p className="panel-note">No authentication activity recorded yet.</p>}
        </div>
      </section>

      {creating && (
        <Modal title="Create organizer" onClose={() => setCreating(false)}>
          <form className="modal-form" onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); create.mutate(event.currentTarget); }}>
            <Field label="Display name" name="display_name" required autoFocus />
            <Field label="Email" name="email" type="email" autoComplete="off" required />
            <label className="field"><span>Role</span><select name="role" defaultValue="admin"><option value="admin">Admin</option><option value="owner">Owner</option></select><small>Owners can manage other organizer accounts.</small></label>
            {create.isError && <div className="form-error">{create.error.message}</div>}
            <div className="modal-actions"><Button variant="secondary" type="button" onClick={() => setCreating(false)}>Cancel</Button><Button busy={create.isPending}>Create and generate link</Button></div>
          </form>
        </Modal>
      )}
      {setupUrl && (
        <Modal title="Password setup link" onClose={() => setSetupUrl("")}>
          <div className="modal-form">
            <p>Send this one-time link securely to the organizer. It expires in 24 hours.</p>
            <div className="share-box"><div><code>{setupUrl}</code><Button variant="quiet" onClick={() => navigator.clipboard.writeText(setupUrl)}>Copy</Button></div></div>
            <div className="modal-actions"><Button onClick={() => setSetupUrl("")}>Done</Button></div>
          </div>
        </Modal>
      )}
    </main>
  );
}

function AccountSecurity() {
  const change = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const data = new FormData(form);
      const password = String(data.get("password"));
      if (password !== data.get("confirm_password")) throw new Error("New passwords do not match");
      return api("/api/v1/auth/password", {
        method: "POST",
        body: JSON.stringify({ current_password: data.get("current_password"), password }),
      });
    },
    onSuccess: () => {
      setCsrfToken(null);
      window.location.assign("/admin");
    },
  });
  return (
    <main className="admin-content">
      <PageTitle eyebrow="Account security" title="Change password" subtitle="Changing your password signs out your existing organizer session." />
      <section className="panel security-panel">
        <form className="modal-form" onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); change.mutate(event.currentTarget); }}>
          <Field label="Current password" name="current_password" type="password" autoComplete="current-password" required />
          <Field label="New password" name="password" type="password" minLength={12} maxLength={128} autoComplete="new-password" hint="Use at least 12 characters." required />
          <Field label="Confirm new password" name="confirm_password" type="password" minLength={12} maxLength={128} autoComplete="new-password" required />
          {change.isError && <div className="form-error">{change.error.message}</div>}
          <Button busy={change.isPending}>Change password</Button>
        </form>
      </section>
    </main>
  );
}

function PageTitle({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle: string }) {
  return <div className="page-title"><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{subtitle}</p></div>;
}
function Stat({ icon, value, label, accent }: { icon: React.ReactNode; value: number; label: string; accent: string }) {
  return <div className={`stat stat--${accent}`}><div className="stat__icon">{icon}</div><span><strong>{value}</strong><small>{label}</small></span></div>;
}
function MeetingRow({ meeting }: { meeting: Meeting }) {
  return <div className="meeting-row"><MeetingRowContent meeting={meeting} /></div>;
}
function MeetingRowContent({ meeting }: { meeting: Meeting }) {
  return <><div className="date-tile"><strong>{new Date(meeting.starts_at).toLocaleDateString("en-US", { day: "2-digit", timeZone: "America/New_York" })}</strong><span>{new Date(meeting.starts_at).toLocaleDateString("en-US", { month: "short", timeZone: "America/New_York" })}</span></div><div className="meeting-row__body"><strong>{meeting.title}</strong><span>{formatMeetingDate(meeting.starts_at)}</span></div><StatusBadge status={meeting.status} /><span className="meeting-row__count"><strong>{meeting.checkin_count ?? 0}</strong> checked in</span></>;
}
function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><div className="modal"><div className="modal__head"><h2>{title}</h2><button className="icon-button" onClick={onClose}><X /></button></div>{children}</div></div>;
}
function PageLoading() {
  return <main className="admin-content"><div className="admin-skeleton"><div /><div /><div /></div></main>;
}
