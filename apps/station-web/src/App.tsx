import { useEffect, useState } from "react";

import { bootstrapSession, fetchAppStatus } from "./api/client";
import type { AppStatus } from "./api/types";
import { AppShell } from "./components/AppShell";

export default function App() {
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [connectionError, setConnectionError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load(): Promise<void> {
      try {
        // The cookie was set by the one-shot /session/<token> redirect; this
        // exchanges it for the in-memory CSRF value.
        await bootstrapSession();
        const next = await fetchAppStatus();
        if (!cancelled) {
          setStatus(next);
          setConnectionError(false);
        }
      } catch {
        if (!cancelled) {
          setStatus(null);
          setConnectionError(true);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return <AppShell connectionError={connectionError} loading={loading} status={status} />;
}
