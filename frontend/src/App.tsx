import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarX2, LockKeyhole } from "lucide-react";

import { AdminPage } from "./AdminPage";
import { CheckinPage } from "./CheckinPage";
import { SetupPasswordPage } from "./SetupPasswordPage";
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
      <main className="route-page">
        <header className="route-page__title">
          <div className="eyebrow">Phoenixville Democrats</div>
          <h1>Meeting Check-In</h1>
        </header>
        <section className="route-page__message">
          <div className="empty-state__icon">
            {active.isError ? <LockKeyhole /> : <CalendarX2 />}
          </div>
          <div>
            <h2>{active.isError ? "Check-in is temporarily unavailable" : "No meeting is active"}</h2>
            <p>
              {active.isError
                ? "Please try again shortly or ask an organizer for help."
                : "When a monthly meeting opens for check-in, the form will appear on this page."}
            </p>
            <a className="text-link" href="/admin">Organizer sign-in →</a>
          </div>
        </section>
        <div className="route-page__footer">
          Paid for by the Phoenixville Democratic Committee.
        </div>
      </main>
    </div>
  );
}

export default function App() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path.startsWith("/setup-password/")) {
    return (
      <SetupPasswordPage
        token={decodeURIComponent(path.slice("/setup-password/".length))}
      />
    );
  }
  if (path.startsWith("/admin")) return <AdminPage />;
  if (path.startsWith("/checkin/")) {
    return <CheckinPage token={decodeURIComponent(path.slice("/checkin/".length))} />;
  }
  return <ActiveMeetingLanding />;
}
