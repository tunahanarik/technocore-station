import { Alert, Tabs } from "@heroui/react";

import type { AppStatus } from "../api/types";
import { ComposeVerifyPage } from "../pages/ComposeVerifyPage";
import { EvidencePage } from "../pages/EvidencePage";
import { IdentityPage } from "../pages/IdentityPage";
import { SystemStatusBar } from "./SystemStatusBar";
import { ThemeToggle } from "./ThemeToggle";

interface AppShellProps {
  readonly status: AppStatus | null;
  readonly loading: boolean;
  readonly connectionError: boolean;
}

/**
 * Application shell.
 *
 * Top tabs, no sidebar (ADR-002): three surfaces is not enough navigation to
 * justify a rail, and an empty rail invites filling it with modules that do
 * not exist yet.
 */
export function AppShell({ status, loading, connectionError }: AppShellProps) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-4 sm:px-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex flex-col gap-0.5">
              <h1 className="text-lg font-semibold text-foreground">Technocore Station</h1>
              <p className="text-sm text-muted">
                Yerel agent kimlik, imzalama ve kanit istasyonu
              </p>
            </div>
            <ThemeToggle />
          </div>

          <SystemStatusBar loading={loading} status={status} />
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        {connectionError && (
          <Alert className="mb-4" status="danger">
            <Alert.Indicator />
            <Alert.Content>
              <Alert.Title>Yerel cekirdege baglanilamadi</Alert.Title>
              <Alert.Description>
                Oturum bulunamadi veya yerel servis yanit vermiyor. Uygulamayi
                launcher uzerinden yeniden acin; acilis baglantisi tek
                kullanimliktir ve 30 saniye sonra gecersiz olur.
              </Alert.Description>
            </Alert.Content>
          </Alert>
        )}

        <Tabs defaultSelectedKey="identity">
          <Tabs.ListContainer>
            <Tabs.List aria-label="Ana bolumler">
              <Tabs.Tab id="identity">
                Identity
                <Tabs.Indicator />
              </Tabs.Tab>
              <Tabs.Tab id="compose">
                Compose &amp; Verify
                <Tabs.Indicator />
              </Tabs.Tab>
              <Tabs.Tab id="evidence">
                Evidence &amp; Sources
                <Tabs.Indicator />
              </Tabs.Tab>
            </Tabs.List>
          </Tabs.ListContainer>

          <Tabs.Panel className="pt-5" id="identity">
            <IdentityPage />
          </Tabs.Panel>
          <Tabs.Panel className="pt-5" id="compose">
            <ComposeVerifyPage />
          </Tabs.Panel>
          <Tabs.Panel className="pt-5" id="evidence">
            <EvidencePage />
          </Tabs.Panel>
        </Tabs>
      </main>

      <footer className="mx-auto max-w-6xl px-4 pb-8 sm:px-6">
        <p className="text-xs text-muted">
          Asama 1 - guvenli yerel iskelet. Gercek DID olusturulmadi ve
          Technocore&apos;a hicbir yazma istegi gonderilmedi.
        </p>
      </footer>
    </div>
  );
}
