import { useCallback, useEffect, useState } from "react";

import { type ApiError, bootstrapSession, fetchAppStatus, toApiError } from "./api/client";
import type { AppStatus } from "./api/types";
import { AppShell } from "./components/AppShell";

export default function App() {
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [connectionError, setConnectionError] = useState<ApiError | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    try {
      // The cookie was set by the one-shot /session/<token> redirect; this
      // exchanges it for the in-memory CSRF value.
      await bootstrapSession();
      setStatus(await fetchAppStatus());
      setConnectionError(null);
    } catch (caught) {
      setStatus(null);
      setConnectionError(toApiError(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <AppShell
      connectionError={connectionError}
      loading={loading}
      onRetryConnection={() => void load()}
      status={status}
    />
  );
}
