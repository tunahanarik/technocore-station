import { Alert, Button, Card, Separator } from "@heroui/react";
import { useCallback, useEffect, useState } from "react";

import { type ApiError, fetchConformance, fetchIdentity, toApiError } from "../api/client";
import type { ConformanceStatus, IdentityStatus } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorRegion } from "../components/ErrorRegion";
import { StatusPill } from "../components/StatusPill";
import {
  AdoptRecoveryDialog,
  CreateIdentityDialog,
  ExportRecoveryDialog,
  RestoreTestDialog,
  RevokeIdentityDialog,
} from "../components/identity/IdentityDialogs";
import { identityStateLabel, identityStateTone, nextAction } from "../lib/identityGuidance";

/**
 * Identity surface, driven by the backend state machine.
 *
 * The page shows public material only: DID, fingerprint, protection mode and
 * recovery timestamps. There is no seed field, no seed display and no copy
 * control for anything secret.
 */

type DialogName = "create" | "export" | "restore" | "adopt" | "revoke" | null;

/**
 * Turkish labels for the self-test's contract areas.
 *
 * `unicode_database` is deliberately absent: it is a version comparison
 * rather than a protocol capability, and it is reported with the other
 * runtime versions below.
 */
const CAPABILITY_LABELS: Record<string, string> = {
  sweep: "Sweep",
  did: "DID",
  canonical: "Canonical",
  signing: "Imzalama",
  verification: "Dogrulama",
  encoding: "base64url",
  tamper: "Tamper reddi",
};

/** The conformance block inside "Teknik ayrintilar". */
function ConformancePanel({
  conformance,
  error,
  onRetry,
  retryPending,
}: {
  readonly conformance: ConformanceStatus | null;
  readonly error: ApiError | null;
  readonly onRetry: () => void;
  readonly retryPending: boolean;
}) {
  if (error !== null) {
    return (
      <ErrorRegion
        error={error}
        onRetry={onRetry}
        retryPending={retryPending}
        section="Kimlik ve Guvenlik / Protokol uygunlugu"
        title="Uygunluk durumu okunamadi"
      />
    );
  }
  if (conformance === null) {
    return <p className="text-sm text-muted">Uygunluk durumu okunuyor...</p>;
  }

  // Own-property check, not `in`: `in` also matches the prototype chain, so a
  // backend check named "toString" would resolve to a function and render as
  // a nonsense label.
  const areas = conformance.checks.filter((check) =>
    Object.hasOwn(CAPABILITY_LABELS, check.name),
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-foreground">Protokol uygunlugu</h3>
        <StatusPill
          label={conformance.passed ? "Asama 2B · Hazir" : "Asama 2B · Basarisiz"}
          tone={conformance.passed ? "ok" : "problem"}
        />
      </div>

      <p className="text-xs text-muted">
        Bu sonuc, bu yapinin <strong>pinlenmis referans commit</strong> ile ayni
        davrandigini gosterir. Canli Technocore sunucusunun hala ayni protokolde
        oldugunu <strong>gostermez</strong>; o kontrol Asama 3'te gelir.
      </p>

      <div className="flex flex-wrap gap-2">
        {areas.map((check) => (
          <StatusPill
            key={check.name}
            label={`${CAPABILITY_LABELS[check.name]} (${String(check.vectors)})`}
            tone={check.passed ? "ok" : "problem"}
          />
        ))}
      </div>

      {!conformance.passed && conformance.failures.length > 0 && (
        <ul className="flex flex-col gap-1">
          {conformance.failures.map((failure) => (
            <li key={failure} className="text-xs text-danger">
              {failure}
            </li>
          ))}
        </ul>
      )}

      <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs text-muted sm:grid-cols-2">
        <div className="flex justify-between gap-2">
          <dt>Pinlenmis referans</dt>
          <dd className="font-mono">{conformance.upstream_commit_short}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Vektor paketi</dt>
          {/* Short form only: the full digest is 64 hex characters, the same
              shape as a seed, and this surface renders no such run. */}
          <dd className="font-mono">{conformance.bundle_digest_short}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Vektor sayisi</dt>
          <dd className="font-mono">{conformance.bundle_vectors}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Paket surumu</dt>
          <dd className="font-mono">{conformance.package_version}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Python</dt>
          <dd className="font-mono">{conformance.python_version}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Unicode veritabani</dt>
          <dd className="font-mono">
            {conformance.unicode_version}
            {conformance.unicode_version_matches ? "" : " (uyusmuyor)"}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function formatDate(value: string | null): string {
  if (value === null) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("tr-TR");
}

function CopyableValue({ label, value }: { readonly label: string; readonly value: string }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(value);
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 2000);
    } catch {
      // Clipboard access can be refused; say so instead of silently resetting.
      setCopyState("failed");
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-semibold tracking-wide text-muted uppercase">{label}</span>
      <div className="flex flex-wrap items-center gap-2">
        <code className="rounded bg-surface-secondary px-2 py-1 text-xs break-all">{value}</code>
        <Button aria-label={`${label} degerini kopyala`} onPress={() => void copy()} size="sm" variant="secondary">
          {copyState === "copied" ? "Kopyalandi" : copyState === "failed" ? "Kopyalanamadi" : "Kopyala"}
        </Button>
      </div>
    </div>
  );
}

export function IdentityPage() {
  const [status, setStatus] = useState<IdentityStatus | null>(null);
  const [conformance, setConformance] = useState<ConformanceStatus | null>(null);
  const [conformanceError, setConformanceError] = useState<ApiError | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  // Tracked separately from `loading` so a failed conformance read can disable
  // its own retry without the identity surface waiting on it.
  const [conformanceLoading, setConformanceLoading] = useState(true);
  const [dialog, setDialog] = useState<DialogName>(null);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setConformanceLoading(true);
    try {
      setStatus(await fetchIdentity());
      setError(null);
    } catch (caught) {
      setError(toApiError(caught));
    } finally {
      setLoading(false);
    }

    // Loaded separately, and never allowed to block the identity surface: a
    // conformance read that fails is shown on its own panel rather than
    // hiding the identity the user came here for.
    try {
      setConformance(await fetchConformance());
      setConformanceError(null);
    } catch (caught) {
      setConformance(null);
      setConformanceError(toApiError(caught));
    } finally {
      setConformanceLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && status === null) {
    return (
      <Card>
        <Card.Header>
          <Card.Title>Kimlik</Card.Title>
        </Card.Header>
        <Card.Content>
          <p className="text-sm text-muted">Durum okunuyor...</p>
        </Card.Content>
      </Card>
    );
  }

  if (status === null) {
    return (
      <Card>
        <Card.Header>
          <Card.Title>Kimlik</Card.Title>
        </Card.Header>
        <Card.Content className="flex flex-col gap-4">
          {error !== null && (
            <ErrorRegion
              error={error}
              onRetry={() => void load()}
              retryPending={loading}
              section="Kimlik ve Guvenlik"
              title="Kimlik durumu okunamadi"
            />
          )}
        </Card.Content>
      </Card>
    );
  }

  const identity = status.identity;
  const capability = status.capability;
  const recoveryVerified = status.recovery.verified_at !== null;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <Card.Header className="gap-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Card.Title>Kimlik</Card.Title>
            <StatusPill label={identityStateLabel(status)} tone={identityStateTone(status)} />
          </div>
          <Card.Description>
            DID, koruma, recovery ve secret yasam dongusu bu yuzeyde yonetilir.
          </Card.Description>
        </Card.Header>

        <Card.Content className="flex flex-col gap-4">
          {!capability.usable && (
            <Alert status="danger">
              <Alert.Indicator />
              <Alert.Content>
                <Alert.Title>Secret kasasi kullanilamiyor</Alert.Title>
                <Alert.Description>{capability.detail}</Alert.Description>
              </Alert.Content>
            </Alert>
          )}

          {error !== null && (
            <ErrorRegion
              error={error}
              onRetry={() => void load()}
              retryPending={loading}
              section="Kimlik ve Guvenlik"
              title="Son islem basarisiz oldu"
            />
          )}

          {identity === null ? (
            <EmptyState
              description="Bu bilgisayarda henuz bir Ed25519 did:key kimligi olusturulmadi ve iceri aktarilmadi."
              title="Kimlik olusturulmadi"
            />
          ) : (
            <div className="flex flex-col gap-4">
              <CopyableValue label="Public DID" value={identity.did} />
              <CopyableValue label="Public fingerprint" value={identity.fingerprint_short} />

              <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <dt className="text-xs font-semibold tracking-wide text-muted uppercase">
                    Koruma
                  </dt>
                  <dd className="text-sm">
                    {identity.protection === "dpapi+passphrase"
                      ? "DPAPI + parola"
                      : identity.protection === "dpapi"
                        ? "Yalniz DPAPI"
                        : "-"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold tracking-wide text-muted uppercase">
                    Olusturulma
                  </dt>
                  <dd className="text-sm">{formatDate(identity.created_at)}</dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold tracking-wide text-muted uppercase">
                    Recovery olusturuldu
                  </dt>
                  <dd className="flex items-center gap-2 text-sm">
                    <StatusPill
                      label={status.recovery.exported_at === null ? "Hayir" : "Evet"}
                      tone={status.recovery.exported_at === null ? "pending" : "ok"}
                    />
                    <span>{formatDate(status.recovery.exported_at)}</span>
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold tracking-wide text-muted uppercase">
                    Restore-test
                  </dt>
                  <dd className="flex items-center gap-2 text-sm">
                    <StatusPill
                      label={recoveryVerified ? "Dogrulandi" : "Bekliyor"}
                      tone={recoveryVerified ? "ok" : "pending"}
                    />
                    <span>{formatDate(status.recovery.verified_at)}</span>
                  </dd>
                </div>
              </dl>
            </div>
          )}

          <Separator />

          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-foreground">Sonraki guvenli adim</h3>
            <p className="text-sm text-muted">{nextAction(status)}</p>
          </div>

          <div className="flex flex-wrap gap-2">
            {/* capability_error is included so the user still sees which
                action is blocked, rather than an empty panel. */}
            {(status.state === "no_identity" || status.state === "capability_error") && (
              <>
                <Button isDisabled={!capability.usable} onPress={() => setDialog("create")}>
                  Yeni kimlik olustur
                </Button>
                <Button
                  isDisabled={!capability.usable}
                  onPress={() => setDialog("adopt")}
                  variant="secondary"
                >
                  Recovery dosyasindan kur
                </Button>
              </>
            )}

            {(status.state === "recovery_pending" || status.state === "ready") && (
              <>
                <Button onPress={() => setDialog("export")} variant="secondary">
                  Recovery dosyasi olustur
                </Button>
                <Button onPress={() => setDialog("restore")}>Restore-test yap</Button>
                <Button onPress={() => setDialog("revoke")} variant="danger">
                  Revoke et
                </Button>
              </>
            )}

            {status.state === "revoked" && (
              <Button isDisabled={!capability.usable} onPress={() => setDialog("create")}>
                Yeni kimlik olustur
              </Button>
            )}
          </div>
        </Card.Content>
      </Card>

      <Card>
        <Card.Header>
          <Card.Title>Teknik ayrintilar</Card.Title>
          <Card.Description>Kasa yetenegi ve dis yazma kapisi.</Card.Description>
        </Card.Header>
        <Card.Content className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill
              label={capability.dpapi_available ? "DPAPI hazir" : "DPAPI yok"}
              tone={capability.dpapi_available ? "ok" : "problem"}
            />
            <StatusPill
              label={capability.aead_available ? "AEAD hazir" : "AEAD yok"}
              tone={capability.aead_available ? "ok" : "problem"}
            />
          </div>

          <Separator />

          <ConformancePanel
            conformance={conformance}
            error={conformanceError}
            onRetry={() => void load()}
            retryPending={conformanceLoading}
          />

          <Separator />

          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-foreground">Dis yazma kapisi</h3>
            <ul className="flex flex-col gap-1">
              {status.gate.checks.map((check) => (
                <li
                  key={check.key}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border px-3 py-2"
                >
                  <span className="text-xs text-muted">{check.detail}</span>
                  <StatusPill
                    label={
                      check.state === "passed"
                        ? "Gecti"
                        : check.state === "not_implemented"
                          ? `Asama ${check.stage}`
                          : "Kapali"
                    }
                    tone={
                      check.state === "passed"
                        ? "ok"
                        : check.state === "not_implemented"
                          ? "inactive"
                          : "pending"
                    }
                  />
                </li>
              ))}
            </ul>
          </div>

          <Alert status="default">
            <Alert.Indicator />
            <Alert.Content>
              <Alert.Title>Secret bu bilgisayardan cikmaz</Alert.Title>
              <Alert.Description>
                Seed yalniz yerelde kalir ve Windows DPAPI ile korunur. Hicbir
                zaman arayuze, API yanitina, loga veya bir dil modeline
                gonderilmez. Bu ekranda bilerek hicbir secret giris veya
                gosterim alani yoktur.
              </Alert.Description>
            </Alert.Content>
          </Alert>
        </Card.Content>
      </Card>

      <CreateIdentityDialog
        isOpen={dialog === "create"}
        onClose={() => setDialog(null)}
        onUpdated={setStatus}
        status={status}
      />
      <ExportRecoveryDialog
        isOpen={dialog === "export"}
        onClose={() => setDialog(null)}
        onUpdated={setStatus}
        status={status}
      />
      <RestoreTestDialog
        isOpen={dialog === "restore"}
        onClose={() => setDialog(null)}
        onUpdated={setStatus}
        status={status}
      />
      <AdoptRecoveryDialog
        isOpen={dialog === "adopt"}
        onClose={() => setDialog(null)}
        onUpdated={setStatus}
        status={status}
      />
      <RevokeIdentityDialog
        isOpen={dialog === "revoke"}
        onClose={() => setDialog(null)}
        onUpdated={setStatus}
        status={status}
      />
    </div>
  );
}
