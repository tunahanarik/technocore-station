import { Button, Card } from "@heroui/react";
import { type ReactNode, useCallback, useEffect, useState } from "react";

import {
  type ApiError,
  fetchConformance,
  fetchIdentity,
  fetchTechnocore,
  toApiError,
} from "../api/client";
import type {
  AppStatus,
  ConformanceStatus,
  DriftState,
  IdentityStatus,
  TechnocoreStatus,
} from "../api/types";
import { ErrorRegion } from "../components/ErrorRegion";
import { StatusPill, type StatusTone } from "../components/StatusPill";
import { SystemStatusBar } from "../components/SystemStatusBar";
import { identityStateLabel, identityStateTone, nextAction } from "../lib/identityGuidance";
import type { SectionId } from "../sections";

/**
 * Genel Bakis: a composition of what the other sections already know.
 *
 * Summaries only - no hash runs, no decorative metrics, no charts. Every
 * card ends in a "go to the section" action; the detail lives where the
 * action does. Each block reads its own endpoint and fails independently,
 * so one unreachable endpoint does not blank the whole overview.
 */

const DRIFT_LABEL: Record<DriftState, string> = {
  never_checked: "Henuz denetlenmedi",
  current: "Guncel",
  drifted: "Suruklenme tespit edildi",
  unavailable: "Erisilemiyor",
};

const DRIFT_TONE: Record<DriftState, StatusTone> = {
  never_checked: "inactive",
  current: "ok",
  drifted: "problem",
  unavailable: "pending",
};

function formatDate(value: string | null): string {
  if (value === null) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("tr-TR");
}

interface OverviewPageProps {
  readonly status: AppStatus | null;
  readonly loading: boolean;
  readonly onNavigate: (section: SectionId) => void;
}

/** Shared frame: title row with a status pill, body, then the section link. */
function SummaryCard({
  title,
  pill,
  goLabel,
  onGo,
  children,
}: {
  readonly title: string;
  readonly pill: ReactNode;
  readonly goLabel: string;
  readonly onGo: () => void;
  readonly children: ReactNode;
}) {
  return (
    <Card className="h-full">
      <Card.Header className="gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Card.Title className="text-base">{title}</Card.Title>
          {pill}
        </div>
      </Card.Header>
      <Card.Content className="flex h-full flex-col gap-3">
        <div className="flex flex-1 flex-col gap-2">{children}</div>
        <div>
          <Button onPress={onGo} size="sm" variant="secondary">
            {goLabel}
          </Button>
        </div>
      </Card.Content>
    </Card>
  );
}

export function OverviewPage({ status, loading, onNavigate }: OverviewPageProps) {
  const [identity, setIdentity] = useState<IdentityStatus | null>(null);
  const [identityError, setIdentityError] = useState<ApiError | null>(null);
  const [technocore, setTechnocore] = useState<TechnocoreStatus | null>(null);
  const [technocoreError, setTechnocoreError] = useState<ApiError | null>(null);
  const [conformance, setConformance] = useState<ConformanceStatus | null>(null);
  const [conformanceError, setConformanceError] = useState<ApiError | null>(null);
  // One flag for all three cards on purpose: every card's retry re-runs the
  // same load, so while it is in flight no card's retry may start another.
  const [refreshing, setRefreshing] = useState(true);

  const load = useCallback(async (): Promise<void> => {
    setRefreshing(true);
    // Three independent reads: each failure is its own finding, shown on its
    // own card, and one does not hide the other two.
    try {
      setIdentity(await fetchIdentity());
      setIdentityError(null);
    } catch (caught) {
      setIdentity(null);
      setIdentityError(toApiError(caught));
    }
    try {
      setTechnocore(await fetchTechnocore());
      setTechnocoreError(null);
    } catch (caught) {
      setTechnocore(null);
      setTechnocoreError(toApiError(caught));
    }
    try {
      setConformance(await fetchConformance());
      setConformanceError(null);
    } catch (caught) {
      setConformance(null);
      setConformanceError(toApiError(caught));
    }
    setRefreshing(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const driftState: DriftState = technocore?.state ?? "never_checked";

  return (
    <div className="flex flex-col gap-4">
      <SystemStatusBar loading={loading} status={status} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <SummaryCard
          goLabel="Kimlik ve Guvenlik bolumune git"
          onGo={() => onNavigate("identity")}
          pill={
            identity !== null ? (
              <StatusPill label={identityStateLabel(identity)} tone={identityStateTone(identity)} />
            ) : (
              <StatusPill label="Bilinmiyor" tone={identityError !== null ? "problem" : "pending"} />
            )
          }
          title="Kimlik"
        >
          {identityError !== null && (
            <ErrorRegion
              error={identityError}
              onRetry={() => void load()}
              retryPending={refreshing}
              section="Genel Bakis / Kimlik ozeti"
              title="Kimlik ozeti okunamadi"
            />
          )}
          {identity === null && identityError === null && (
            <p className="text-sm text-muted">Durum okunuyor...</p>
          )}
          {identity !== null && (
            <>
              <dl className="flex flex-col gap-1 text-sm">
                <div className="flex justify-between gap-2">
                  <dt className="text-muted">Kimlik</dt>
                  <dd>{identity.identity === null ? "Yok" : "Var"}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted">Koruma</dt>
                  <dd>
                    {identity.identity?.protection === "dpapi+passphrase"
                      ? "DPAPI + parola"
                      : identity.identity?.protection === "dpapi"
                        ? "Yalniz DPAPI"
                        : "-"}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted">Recovery</dt>
                  <dd>
                    {identity.recovery.verified_at !== null
                      ? "Dogrulandi"
                      : identity.recovery.exported_at !== null
                        ? "Test bekliyor"
                        : "Olusturulmadi"}
                  </dd>
                </div>
              </dl>
              <p className="text-xs text-muted">
                <span className="font-semibold">Sonraki guvenli adim: </span>
                {nextAction(identity)}
              </p>
            </>
          )}
        </SummaryCard>

        <SummaryCard
          goLabel="Kaynaklar bolumune git"
          onGo={() => onNavigate("sources")}
          pill={<StatusPill label={DRIFT_LABEL[driftState]} tone={DRIFT_TONE[driftState]} />}
          title="Technocore durumu"
        >
          {technocoreError !== null && (
            <ErrorRegion
              error={technocoreError}
              onRetry={() => void load()}
              retryPending={refreshing}
              section="Genel Bakis / Technocore ozeti"
              title="Technocore ozeti okunamadi"
            />
          )}
          {technocore === null && technocoreError === null && (
            <p className="text-sm text-muted">Durum okunuyor...</p>
          )}
          {technocore !== null && (
            <>
              <dl className="flex flex-col gap-1 text-sm">
                <div className="flex justify-between gap-2">
                  <dt className="text-muted">Son basarili kontrol</dt>
                  <dd className="font-mono text-xs">{formatDate(technocore.last_success_at)}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted">Son deneme</dt>
                  <dd className="font-mono text-xs">{formatDate(technocore.last_attempt_at)}</dd>
                </div>
              </dl>
              {technocore.state === "never_checked" && (
                <p className="text-xs text-muted">
                  Station kendiliginden hicbir istek gondermez. Denetim, Kaynaklar
                  bolumundeki acik kullanici eylemiyle baslar.
                </p>
              )}
            </>
          )}
        </SummaryCard>

        <SummaryCard
          goLabel="Kimlik ve Guvenlik bolumune git"
          onGo={() => onNavigate("identity")}
          pill={
            conformance !== null ? (
              <StatusPill
                label={conformance.passed ? "Hazir" : "Basarisiz"}
                tone={conformance.passed ? "ok" : "problem"}
              />
            ) : (
              <StatusPill
                label="Bilinmiyor"
                tone={conformanceError !== null ? "problem" : "pending"}
              />
            )
          }
          title="Protokol uygunlugu"
        >
          {conformanceError !== null && (
            <ErrorRegion
              error={conformanceError}
              onRetry={() => void load()}
              retryPending={refreshing}
              section="Genel Bakis / Uygunluk ozeti"
              title="Uygunluk ozeti okunamadi"
            />
          )}
          {conformance === null && conformanceError === null && (
            <p className="text-sm text-muted">Durum okunuyor...</p>
          )}
          {conformance !== null && (
            <p className="text-sm text-muted">
              {`Self-test ${conformance.passed ? "gecti" : "gecmedi"}: ${String(conformance.bundle_vectors)} vektor, pinlenmis referans ${conformance.upstream_commit_short}.`}{" "}
              Ayrintilar Kimlik ve Guvenlik bolumundeki teknik panelde.
            </p>
          )}
        </SummaryCard>
      </div>
    </div>
  );
}
