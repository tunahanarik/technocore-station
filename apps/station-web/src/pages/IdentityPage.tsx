import { Alert, Button, Card, Separator } from "@heroui/react";
import { useCallback, useEffect, useState } from "react";

import { fetchIdentity } from "../api/client";
import type { IdentityStatus } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { StatusPill, type StatusTone } from "../components/StatusPill";
import {
  AdoptRecoveryDialog,
  CreateIdentityDialog,
  ExportRecoveryDialog,
  RestoreTestDialog,
  RevokeIdentityDialog,
} from "../components/identity/IdentityDialogs";

/**
 * Identity surface, driven by the backend state machine.
 *
 * The page shows public material only: DID, fingerprint, protection mode and
 * recovery timestamps. There is no seed field, no seed display and no copy
 * control for anything secret.
 */

type DialogName = "create" | "export" | "restore" | "adopt" | "revoke" | null;

function formatDate(value: string | null): string {
  if (value === null) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("tr-TR");
}

/** The single safest thing to do next, given the current state. */
function nextAction(status: IdentityStatus): string {
  switch (status.state) {
    case "capability_error":
      return "Secret kasasi kullanilamiyor. Uygulamayi Windows uzerinde calistirin.";
    case "no_identity":
      return "Yeni bir kimlik olusturun veya mevcut bir recovery dosyasindan kurun.";
    case "creating":
      return "Kimlik olusturuluyor.";
    case "recovery_pending":
      return status.recovery.exported_at === null
        ? "Recovery dosyasi olusturun."
        : "Restore-test yaparak recovery dosyasini dogrulayin.";
    case "ready":
      return "Kimlik hazir. Sonraki adim Asama 2B uygunluk motorudur.";
    case "revoked":
      return "Kimlik revoke edildi. Yeni bir kimlik olusturabilirsiniz.";
  }
}

function CopyableValue({ label, value }: { readonly label: string; readonly value: string }) {
  const [copied, setCopied] = useState(false);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-semibold tracking-wide text-muted uppercase">{label}</span>
      <div className="flex flex-wrap items-center gap-2">
        <code className="rounded bg-surface-secondary px-2 py-1 text-xs break-all">{value}</code>
        <Button aria-label={`${label} degerini kopyala`} onPress={() => void copy()} size="sm" variant="secondary">
          {copied ? "Kopyalandi" : "Kopyala"}
        </Button>
      </div>
    </div>
  );
}

function stateTone(status: IdentityStatus): StatusTone {
  switch (status.state) {
    case "ready":
      return "ok";
    case "recovery_pending":
    case "creating":
      return "pending";
    case "no_identity":
      return "inactive";
    case "revoked":
    case "capability_error":
      return "problem";
  }
}

function stateLabel(status: IdentityStatus): string {
  switch (status.state) {
    case "ready":
      return "Hazir";
    case "recovery_pending":
      return "Recovery bekliyor";
    case "creating":
      return "Olusturuluyor";
    case "no_identity":
      return "Kimlik yok";
    case "revoked":
      return "Revoke edildi";
    case "capability_error":
      return "Kasa kullanilamiyor";
  }
}

export function IdentityPage() {
  const [status, setStatus] = useState<IdentityStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [dialog, setDialog] = useState<DialogName>(null);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    try {
      setStatus(await fetchIdentity());
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Kimlik durumu okunamadi.");
    } finally {
      setLoading(false);
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
          <Alert status="danger">
            <Alert.Indicator />
            <Alert.Content>
              <Alert.Title>Kimlik durumu okunamadi</Alert.Title>
              <Alert.Description>{error ?? "Bilinmeyen hata."}</Alert.Description>
            </Alert.Content>
          </Alert>
          <div>
            <Button onPress={() => void load()}>Tekrar dene</Button>
          </div>
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
            <StatusPill label={stateLabel(status)} tone={stateTone(status)} />
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
            <Alert status="danger">
              <Alert.Indicator />
              <Alert.Content>
                <Alert.Title>Son islem basarisiz oldu</Alert.Title>
                <Alert.Description>{error}</Alert.Description>
              </Alert.Content>
            </Alert>
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
