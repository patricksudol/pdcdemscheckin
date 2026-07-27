export type MeetingStatus = "draft" | "open" | "closed";

export interface Meeting {
  id: string;
  title: string;
  starts_at: string;
  location: string | null;
  attendee_message: string | null;
  status: MeetingStatus;
  public_token?: string;
  checkin_count?: number;
}

export interface Profile {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string | null;
  consented_at: string;
  created_at: string;
}

export interface Checkin {
  id: string;
  checked_in_at: string;
  source: "self" | "admin";
  anonymized_name: string | null;
  profile: Profile | null;
}

export class ApiError extends Error {
  status: number;
  details?: unknown;

  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    throw new ApiError(response.status, body?.message ?? "Something went wrong", body?.details);
  }
  return body as T;
}

export function formatMeetingDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "long",
    timeStyle: "short",
    timeZone: "America/New_York",
  }).format(new Date(value));
}
