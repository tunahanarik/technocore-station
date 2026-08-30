import { Card } from "@heroui/react";

import type { AppStatus, DriftState } from "../api/types";
import { StatusPill, type StatusTone } from "./StatusPill";

/**
 * The four honest states. "never_checked" is not a failure and not a success:
 * it is the accurate description of an application that has contacted nobody,
 * which is what Station does until the user asks it to.
 */
const TECHNOCORE_LABEL: Record<DriftState, string> = {
  never_checked: "Denetlenmedi",
  current: "Salt okunur · guncel",
  drifted: "Suruklenme var",
  unavailable: "Erisilemiyor",
};

const TECHNOCORE_TONE: Record<DriftState, StatusTone> = {
  never_checked: "inactive",
  current: "ok",
  drifted: "problem",
  unavailable: "pending",
};

interface StatusItem {
  readonly id: string;
  readonly title: string;
  readonly tone: StatusTone;
  readonly label: string;
  readonly detail: string;
}

interface SystemStatusBarProps {
  readonly status: AppStatus | null;
  readonly loading: boolean;
}

function buildItems(status: AppStatus | null, loading: boolean): StatusItem[] {
  if (loading) {
    return [
      { id: "service", title: "Yerel servis", tone: "pending", label: "Kontrol ediliyor", detail: "Durum okunuyor." },
      { id: "database", title: "Veritabani", tone: "pending", label: "Kontrol ediliyor", detail: "Durum okunuyor." },
      { id: "session", title: "Oturum guvenligi", tone: "pending", label: "Kontrol ediliyor", detail: "Durum okunuyor." },
      { id: "technocore", title: "Technocore", tone: "pending", label: "Kontrol ediliyor", detail: "Durum okunuyor." },
    ];
  }

  if (status === null) {
    return [
      { id: "service", title: "Yerel servis", tone: "problem", label: "Ulasilamiyor", detail: "Yerel cekirdege baglanilamadi." },
      { id: "database", title: "Veritabani", tone: "problem", label: "Bilinmiyor", detail: "Servise ulasilamadigi icin okunamadi." },
      { id: "session", title: "Oturum guvenligi", tone: "problem", label: "Oturum yok", detail: "Uygulamayi launcher ile yeniden acin." },
      { id: "technocore", title: "Technocore", tone: "problem", label: "Bilinmiyor", detail: "Servise ulasilamadigi icin okunamadi." },
    ];
  }

  const databaseHealthy =
    status.database.state === "ready" &&
    status.database.journal_mode === "wal" &&
    status.database.foreign_keys;

  return [
    {
      id: "service",
      title: "Yerel servis",
      tone: "ok",
      label: "Calisiyor",
      detail: `Yalniz 127.0.0.1 · asama ${status.service.stage} · ${
        status.service.mode === "production" ? "uretim" : "gelistirme"
      }`,
    },
    {
      id: "database",
      title: "Veritabani",
      tone: databaseHealthy ? "ok" : "problem",
      label: databaseHealthy ? "Hazir" : "Beklenmeyen durum",
      detail: `journal: ${status.database.journal_mode} · foreign keys: ${
        status.database.foreign_keys ? "acik" : "kapali"
      } · surum: ${status.database.schema_revision}`,
    },
    {
      id: "session",
      title: "Oturum guvenligi",
      tone: status.session_security.csrf_required ? "ok" : "problem",
      label: status.session_security.csrf_required ? "Korumali" : "Eksik",
      // The Secure flag is genuinely absent on loopback HTTP. Say so rather
      // than implying a guarantee the transport cannot provide.
      detail: "HttpOnly · SameSite=Strict · CSRF zorunlu · loopback HTTP (Secure yok)",
    },
    {
      id: "technocore",
      title: "Technocore",
      tone: TECHNOCORE_TONE[status.technocore.state],
      label: TECHNOCORE_LABEL[status.technocore.state],
      detail: status.technocore.detail,
    },
  ];
}

export function SystemStatusBar({ status, loading }: SystemStatusBarProps) {
  const items = buildItems(status, loading);

  return (
    <section aria-label="Sistem durumu">
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((item) => (
          <li key={item.id}>
            <Card className="h-full gap-1 p-3" variant="secondary">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-semibold tracking-wide text-muted uppercase">
                  {item.title}
                </span>
                <StatusPill label={item.label} tone={item.tone} />
              </div>
              <p className="text-xs text-muted">{item.detail}</p>
            </Card>
          </li>
        ))}
      </ul>
    </section>
  );
}
