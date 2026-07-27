import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { LoaderCircle } from "lucide-react";
import pdcLogoUrl from "./assets/pdc-logo.jpeg";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand ${compact ? "brand--compact" : ""}`}>
      <img
        className="brand__logo"
        src={pdcLogoUrl}
        alt="Phoenixville Democrats"
      />
    </div>
  );
}

export function Button({
  children,
  busy,
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  busy?: boolean;
  variant?: "primary" | "secondary" | "danger" | "quiet";
}) {
  return (
    <button
      className={`button button--${variant} ${className}`.trim()}
      disabled={busy || props.disabled}
      {...props}
    >
      {busy && <LoaderCircle className="spin" size={18} aria-hidden="true" />}
      {children}
    </button>
  );
}

export function Field({
  label,
  hint,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  const id = props.id ?? props.name;
  return (
    <label className="field" htmlFor={id}>
      <span>{label}</span>
      <input id={id} {...props} />
      {hint && <small>{hint}</small>}
    </label>
  );
}

export function EmptyState({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon">{icon}</div>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`status status--${status}`}>{status}</span>;
}
