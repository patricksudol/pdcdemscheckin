import { FormEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  CalendarDays,
  Check,
  ChevronRight,
  Clock3,
  LockKeyhole,
  MapPin,
  ShieldCheck,
} from "lucide-react";

import { api, formatMeetingDate, Meeting } from "./api";
import { Brand, Button, Field } from "./components";

type Step = "email" | "returning" | "update" | "new" | "done";

export function CheckinPage({ token }: { token: string }) {
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [alreadyCheckedIn, setAlreadyCheckedIn] = useState(false);

  const meeting = useQuery({
    queryKey: ["public-meeting", token],
    queryFn: () => api<Meeting>(`/api/v1/public/meetings/${token}`),
    retry: false,
  });

  const lookup = useMutation({
    mutationFn: () =>
      api<{
        found: boolean;
        first_name?: string;
        last_name?: string;
        phone?: string | null;
        already_checked_in?: boolean;
      }>(
        `/api/v1/public/meetings/${token}/lookup`,
        { method: "POST", body: JSON.stringify({ email }) },
      ),
    onSuccess(data) {
      if (data.found) {
        setFirstName(data.first_name ?? "");
        setLastName(data.last_name ?? "");
        setPhone(data.phone ?? "");
        setAlreadyCheckedIn(Boolean(data.already_checked_in));
        setStep(data.already_checked_in ? "done" : "returning");
      } else {
        setStep("new");
      }
    },
  });

  const returning = useMutation({
    mutationFn: (updates: Record<string, string | null> = {}) =>
      api<{ first_name: string }>(`/api/v1/public/meetings/${token}/checkins`, {
        method: "POST",
        body: JSON.stringify({ email, ...updates }),
      }),
    onSuccess(data) {
      setFirstName(data.first_name);
      setStep("done");
    },
  });

  const create = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const data = new FormData(form);
      return api<{ first_name: string }>(`/api/v1/public/meetings/${token}/profiles`, {
        method: "POST",
        body: JSON.stringify({
          first_name: data.get("first_name"),
          last_name: data.get("last_name"),
          phone: data.get("phone") || null,
          email,
          consent: data.get("consent") === "on",
        }),
      });
    },
    onSuccess(data) {
      setFirstName(data.first_name);
      setStep("done");
    },
  });

  if (meeting.isLoading) return <PageShell><LoadingCard /></PageShell>;
  if (meeting.isError) {
    return (
      <PageShell>
        <NoticeCard
          icon={<LockKeyhole />}
          title="This check-in link isn’t available"
          message="Please check the QR code or ask a meeting organizer for help."
        />
      </PageShell>
    );
  }

  const item = meeting.data;
  if (!item) {
    return (
      <PageShell>
        <NoticeCard
          icon={<LockKeyhole />}
          title="This check-in link isn’t available"
          message="Please check the QR code or ask a meeting organizer for help."
        />
      </PageShell>
    );
  }
  if (item.status !== "open") {
    return (
      <PageShell>
        <MeetingHeader meeting={item} />
        <NoticeCard
          icon={<Clock3 />}
          title={item.status === "closed" ? "Check-in has closed" : "Check-in opens soon"}
          message={
            item.status === "closed"
              ? "Thanks for being part of the meeting. An organizer can help with a correction."
              : "An organizer will open this page when it’s time to check in."
          }
        />
      </PageShell>
    );
  }

  return (
    <PageShell>
      <MeetingHeader meeting={item} />
      <main className="checkin-card" aria-live="polite">
        {step === "email" && (
          <>
            <div className="step-label">Meeting check-in</div>
            <h1>Welcome! Let’s get you checked in.</h1>
            <p className="lede">Enter the email you’ve used with us before—or create a profile in one quick step.</p>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                lookup.mutate();
              }}
            >
              <Field
                label="Email address"
                name="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                required
                autoFocus
              />
              <ErrorMessage mutation={lookup} />
              <Button type="submit" busy={lookup.isPending} className="button--wide">
                Continue <ChevronRight size={18} />
              </Button>
            </form>
            <div className="privacy-note">
              <ShieldCheck size={18} />
              <span>Your information is only visible to approved Phoenixville Democrats organizers.</span>
            </div>
          </>
        )}

        {step === "returning" && (
          <>
            <div className="welcome-orb">{firstName.charAt(0).toUpperCase()}</div>
            <div className="step-label">We found your profile</div>
            <h1>Welcome back, {firstName}.</h1>
            <p className="lede">Ready to mark yourself present for this meeting?</p>
            <ErrorMessage mutation={returning} />
            <Button
              busy={returning.isPending}
              className="button--wide"
              onClick={() => returning.mutate({})}
            >
              Check me in <Check size={18} />
            </Button>
            <Button variant="secondary" className="button--wide" onClick={() => setStep("update")}>
              Update my profile first
            </Button>
            <button className="text-button" onClick={() => setStep("email")}>
              That isn’t me
            </button>
          </>
        )}

        {step === "update" && (
          <>
            <div className="step-label">Update your profile</div>
            <h1>Is your information still right?</h1>
            <p className="lede">Update your name or phone number, then we’ll check you in.</p>
            <form
              className="form-grid"
              onSubmit={(event: FormEvent<HTMLFormElement>) => {
                event.preventDefault();
                const data = new FormData(event.currentTarget);
                returning.mutate({
                  first_name: String(data.get("first_name") ?? ""),
                  last_name: String(data.get("last_name") ?? ""),
                  phone: String(data.get("phone") ?? "") || null,
                });
              }}
            >
              <Field label="First name" name="first_name" defaultValue={firstName} autoComplete="given-name" required autoFocus />
              <Field label="Last name" name="last_name" defaultValue={lastName} autoComplete="family-name" required />
              <Field label="Phone (optional)" name="phone" type="tel" defaultValue={phone} autoComplete="tel" placeholder="(610) 555-0123" />
              <ErrorMessage mutation={returning} />
              <Button type="submit" busy={returning.isPending} className="button--wide field--full">
                Save changes & check in <Check size={18} />
              </Button>
            </form>
            <button className="text-button" onClick={() => setStep("returning")}>
              Back
            </button>
          </>
        )}

        {step === "new" && (
          <>
            <div className="step-label">Create your profile</div>
            <h1>Great to meet you.</h1>
            <p className="lede">We’ll save this for faster check-in at future monthly meetings.</p>
            <form
              className="form-grid"
              onSubmit={(event: FormEvent<HTMLFormElement>) => {
                event.preventDefault();
                create.mutate(event.currentTarget);
              }}
            >
              <Field label="First name" name="first_name" autoComplete="given-name" required autoFocus />
              <Field label="Last name" name="last_name" autoComplete="family-name" required />
              <Field
                label="Phone (optional)"
                name="phone"
                type="tel"
                autoComplete="tel"
                placeholder="(610) 555-0123"
              />
              <label className="consent field--full">
                <input type="checkbox" name="consent" required />
                <span>
                  I consent to Phoenixville Democrats storing my contact information and meeting attendance. I can request deletion at any time.
                </span>
              </label>
              <ErrorMessage mutation={create} />
              <Button type="submit" busy={create.isPending} className="button--wide field--full">
                Create profile & check in
              </Button>
            </form>
            <button className="text-button" onClick={() => setStep("email")}>
              Use a different email
            </button>
          </>
        )}

        {step === "done" && (
          <div className="success">
            <div className="success__ring"><Check size={38} strokeWidth={3} /></div>
            <div className="step-label">{alreadyCheckedIn ? "Already recorded" : "You’re checked in"}</div>
            <h1>{alreadyCheckedIn ? `You’re all set, ${firstName}.` : `Thanks for being here, ${firstName}!`}</h1>
            <p className="lede">
              {alreadyCheckedIn
                ? "We already have your attendance for this meeting."
                : "Your attendance has been recorded. You can close this page."}
            </p>
          </div>
        )}
      </main>
    </PageShell>
  );
}

function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="public-shell">
      <header className="public-nav"><Brand /></header>
      <div className="public-content">{children}</div>
      <footer>Paid for by the Phoenixville Democratic Committee.</footer>
    </div>
  );
}

function MeetingHeader({ meeting }: { meeting: Meeting }) {
  return (
    <section className="meeting-intro">
      <div className="eyebrow">Phoenixville Democrats</div>
      <h2>{meeting.title}</h2>
      <div className="meeting-meta">
        <span><CalendarDays size={17} />{formatMeetingDate(meeting.starts_at)}</span>
        {meeting.location && <span><MapPin size={17} />{meeting.location}</span>}
      </div>
      {meeting.attendee_message && <p>{meeting.attendee_message}</p>}
    </section>
  );
}

function NoticeCard({ icon, title, message }: { icon: React.ReactNode; title: string; message: string }) {
  return (
    <main className="checkin-card notice-card">
      <div className="empty-state__icon">{icon}</div>
      <h1>{title}</h1>
      <p className="lede">{message}</p>
    </main>
  );
}

function LoadingCard() {
  return <main className="checkin-card skeleton-card"><div /><div /><div /></main>;
}

function ErrorMessage({ mutation }: { mutation: { isError: boolean; error: Error | null } }) {
  return mutation.isError ? <div className="form-error" role="alert">{mutation.error?.message}</div> : null;
}
