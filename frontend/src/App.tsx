import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarX2, LockKeyhole } from "lucide-react";

import { AdminPage } from "./AdminPage";
import { CheckinPage } from "./CheckinPage";
import { api, Meeting } from "./api";
import { Brand } from "./components";

function ActiveMeetingLanding() {
  const active = useQuery({
    queryKey: ["active-meeting"],
    queryFn: () =>
      api<{ active: boolean; meeting: (Meeting & { public_token: string }) | null }>(
        "/api/v1/public/meetings/active",
      ),
    refetchInterval: 30_000,
  });
  const activeToken = active.data?.active ? active.data.meeting?.public_token : undefined;
  useEffect(() => {
    if (activeToken) window.location.replace(`/checkin/${activeToken}`);
  }, [activeToken]);

  if (active.isLoading) {
    return (
      <div className="home-page home-page--center">
        <Brand />
        <main className="splash-card skeleton-card"><div /><div /><div /></main>
      </div>
    );
  }
  if (activeToken) {
    return (
      <div className="home-page home-page--center">
        <Brand />
        <main className="splash-card skeleton-card"><div /><div /><div /></main>
      </div>
    );
  }
  return (
    <div className="home-page home-page--center">
      <Brand />
      <main className="splash-card">
        <div className="empty-state__icon">
          {active.isError ? <LockKeyhole /> : <CalendarX2 />}
        </div>
        <div className="eyebrow">Monthly meeting check-in</div>
        <h1>{active.isError ? "We can’t load check-in right now." : "No meeting is active."}</h1>
        <p>
          {active.isError
            ? "Please try again shortly or ask an organizer for help."
            : "When a Phoenixville Democrats meeting opens for check-in, it will appear right here."}
        </p>
        <a className="text-link" href="/admin">Organizer sign-in →</a>
      </main>
    </div>
  );
}

export default function App() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path.startsWith("/admin")) return <AdminPage />;
  if (path.startsWith("/checkin/")) {
    return <CheckinPage token={decodeURIComponent(path.slice("/checkin/".length))} />;
  }
  return <ActiveMeetingLanding />;
}
