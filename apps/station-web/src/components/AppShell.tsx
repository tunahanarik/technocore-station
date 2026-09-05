import { Button } from "@heroui/react";
import { useId, useState } from "react";

import type { ApiError } from "../api/client";
import type { AppStatus } from "../api/types";
import { ActivityPage } from "../pages/ActivityPage";
import { ComposeVerifyPage } from "../pages/ComposeVerifyPage";
import { EvidencePage } from "../pages/EvidencePage";
import { IdentityPage } from "../pages/IdentityPage";
import { OverviewPage } from "../pages/OverviewPage";
import { SettingsHelpPage } from "../pages/SettingsHelpPage";
import { SourcesPage } from "../pages/SourcesPage";
import { TasksPage } from "../pages/TasksPage";
import { WorkScanPage } from "../pages/WorkScanPage";
import { DEFAULT_SECTION_ID, READY_SECTIONS, type SectionId } from "../sections";
import { ErrorRegion } from "./ErrorRegion";

interface AppShellProps {
  readonly status: AppStatus | null;
  readonly loading: boolean;
  readonly connectionError: ApiError | null;
  readonly onRetryConnection: () => void;
}

/**
 * Application shell: a left navigation and one mounted section.
 *
 * ADR-0001 item 2 replaced the three-tab MVP layout with a left-nav
 * dashboard. The navigation renders only sections whose registry entry says
 * `ready` - an unbuilt section never appears as an empty menu item.
 *
 * Selection is plain controlled state and only the selected section is
 * mounted, so each page keeps the existing fetch-your-own-data pattern.
 * There is no router and no URL sync (no deep links, no new dependency),
 * and the collapse state is React state only - never browser storage.
 *
 * Collapsing narrows the menu; it never removes it. The `<nav>` landmark and
 * every section button stay in the tree, with the label reduced to an initial
 * for sighted users and kept in full as the button's accessible name. An
 * unmounted landmark would take the whole menu away from a screen-reader user
 * while a sighted user still sees a narrow one.
 */
export function AppShell({ status, loading, connectionError, onRetryConnection }: AppShellProps) {
  const [selected, setSelected] = useState<SectionId>(DEFAULT_SECTION_ID);
  const [collapsed, setCollapsed] = useState(false);
  const navId = useId();

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <div
        className={`flex shrink-0 flex-col gap-2 border-r border-border p-3 ${
          collapsed ? "w-auto" : "w-56"
        }`}
      >
        <div>
          <Button
            aria-controls={navId}
            aria-expanded={!collapsed}
            onPress={() => setCollapsed((current) => !current)}
            size="sm"
            variant="ghost"
          >
            {collapsed ? "Menuyu ac" : "Menuyu daralt"}
          </Button>
        </div>

        <nav aria-label="Ana bolumler" id={navId}>
          <ul className="flex flex-col gap-1">
            {READY_SECTIONS.map((section) => {
              const isSelected = selected === section.id;
              return (
                <li key={section.id}>
                  <button
                    aria-current={isSelected ? "page" : undefined}
                    className={`w-full rounded-lg py-2 text-sm transition-colors focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none ${
                      collapsed ? "px-2 text-center" : "px-3 text-left"
                    } ${
                      isSelected
                        ? "bg-surface-secondary font-semibold text-foreground"
                        : "text-muted hover:bg-surface-secondary/60 hover:text-foreground"
                    }`}
                    onClick={() => setSelected(section.id)}
                    type="button"
                  >
                    {collapsed ? (
                      <>
                        {/* Visual shorthand only. The accessible name stays
                            the full label, so the menu reads identically
                            collapsed or not. */}
                        <span aria-hidden="true">{section.label.slice(0, 1)}</span>
                        <span className="sr-only">{section.label}</span>
                      </>
                    ) : (
                      section.label
                    )}
                    {isSelected && <span className="sr-only"> (secili bolum)</span>}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-border">
          <div className="mx-auto flex max-w-6xl flex-col gap-0.5 px-4 py-4 sm:px-6">
            <h1 className="text-lg font-semibold text-foreground">Technocore Station</h1>
            <p className="text-sm text-muted">
              Yerel agent kimlik, imzalama ve kanit istasyonu
            </p>
          </div>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6">
          {connectionError !== null && (
            <div className="mb-4">
              <ErrorRegion
                error={connectionError}
                onRetry={onRetryConnection}
                retryPending={loading}
                section="Kabuk / Oturum baslatma"
                title="Yerel cekirdege baglanilamadi"
              />
            </div>
          )}

          {selected === "overview" && (
            <OverviewPage loading={loading} onNavigate={setSelected} status={status} />
          )}
          {selected === "work-scan" && <WorkScanPage />}
          {selected === "tasks" && <TasksPage />}
          {selected === "activity" && <ActivityPage />}
          {selected === "identity" && <IdentityPage />}
          {selected === "compose" && <ComposeVerifyPage />}
          {selected === "sources" && <SourcesPage />}
          {selected === "evidence" && <EvidencePage />}
          {selected === "settings" && <SettingsHelpPage status={status} />}
        </main>

        <footer className="mx-auto w-full max-w-6xl px-4 pb-8 sm:px-6">
          <p className="text-xs text-muted">
            Yerel istasyon: veriler bu bilgisayarda kalir ve dis yazma kapisi
            kullanici onayi olmadan acilmaz.
          </p>
        </footer>
      </div>
    </div>
  );
}
