import { FormEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, KeyRound } from "lucide-react";

import { api } from "./api";
import { Brand, Button, Field } from "./components";

export function SetupPasswordPage({ token }: { token: string }) {
  const [complete, setComplete] = useState(false);
  const details = useQuery({
    queryKey: ["password-setup", token],
    queryFn: () =>
      api<{ email: string; display_name: string }>(
        `/api/v1/auth/password-setup/${encodeURIComponent(token)}`,
      ),
    retry: false,
  });
  const setup = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const data = new FormData(form);
      const password = String(data.get("password"));
      if (password !== data.get("confirm_password")) {
        throw new Error("Passwords do not match");
      }
      return api(`/api/v1/auth/password-setup/${encodeURIComponent(token)}`, {
        method: "POST",
        body: JSON.stringify({ password }),
      });
    },
    onSuccess: () => setComplete(true),
  });

  return (
    <div className="login-page">
      <Brand />
      <main className="login-card">
        <div className="welcome-orb">{complete ? <CheckCircle2 /> : <KeyRound />}</div>
        {complete ? (
          <>
            <div className="eyebrow">Account ready</div>
            <h1>Password saved</h1>
            <p>You can now sign in to the organizer workspace.</p>
            <a className="button button--primary button--wide" href="/admin">Organizer sign-in</a>
          </>
        ) : details.isError ? (
          <>
            <div className="eyebrow">Link unavailable</div>
            <h1>Setup link expired</h1>
            <p>Ask an owner to generate a new password setup link for your account.</p>
          </>
        ) : details.data ? (
          <>
            <div className="eyebrow">Organizer account</div>
            <h1>Welcome, {details.data.display_name}</h1>
            <p>Create a password for {details.data.email}. This link works only once.</p>
            <form
              onSubmit={(event: FormEvent<HTMLFormElement>) => {
                event.preventDefault();
                setup.mutate(event.currentTarget);
              }}
            >
              <Field
                label="New password"
                name="password"
                type="password"
                minLength={12}
                maxLength={128}
                autoComplete="new-password"
                hint="Use at least 12 characters."
                required
              />
              <Field
                label="Confirm password"
                name="confirm_password"
                type="password"
                minLength={12}
                maxLength={128}
                autoComplete="new-password"
                required
              />
              {setup.isError && <div className="form-error">{setup.error.message}</div>}
              <Button busy={setup.isPending} className="button--wide">Set password</Button>
            </form>
          </>
        ) : (
          <p>Checking your setup link…</p>
        )}
      </main>
    </div>
  );
}
