import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BarChart3,
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  Download,
  ExternalLink,
  Menu,
  Plus,
  QrCode,
  Search,
  Users,
  X,
} from "lucide-react";

import { api, Checkin, formatMeetingDate, Meeting, MeetingStatus, Profile } from "./api";
import { Brand, Button, EmptyState, Field, StatusBadge } from "./components";

interface Me {
  display_name: string;
  email: string;
  role: string;
}

export function AdminPage() {
  const [menuOpen, setMenuOpen] = useState(false);
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/api/v1/auth/me"), retry: false });

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
          <form method="post" action="/api/v1/auth/logout"><button className="text-button">Sign out</button></form>
        </header>
        {window.location.pathname === "/admin/meetings" ? (
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
      api<{ signed_in: boolean }>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      }),
    onSuccess: onSignedIn,
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
