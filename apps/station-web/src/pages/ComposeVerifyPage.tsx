import { Alert, Card, Separator } from "@heroui/react";
import { useCallback, useEffect, useState } from "react";

import { type ApiError, fetchIdentity, toApiError } from "../api/client";
import type { IdentityStatus } from "../api/types";
import { ComposerPanel } from "../components/compose/ComposerPanel";
import { ErrorRegion } from "../components/ErrorRegion";
import { StatusPill, type StatusTone } from "../components/StatusPill";
import { gateReasonLabel } from "../lib/identityGuidance";

/**
 * Compose & Verify: the three-step outbound write path (Paket D).
 *
 * The surface is no longer a locked screen, but nothing about the lock has
 * been loosened. The preconditions below are the same gate they always were,
 * the composer only appears when the *server* says the gate is open, and all
 * three steps re-run that gate server-side - a rendered form is never what
 * decides whether a write can happen.
 *
 * What the flow guarantees, and why each part exists, is documented on
 * `ComposerPanel`. The short version: draft, then an explicit signing
 * approval, then a separate single-use send approval; editing the content
 * drops all three; and the result is three-valued, with `outcome_unknown`
 * shown as itself rather than flattened into success or failure.
 */

function toneFor(state: string): StatusTone {
  if (state === "passed") return "ok";
  if (state === "not_implemented") return "inactive";
  return "pending";
}

function labelFor(state: string, stage: string): string {
  if (state === "passed") return "Tamam";
  if (state === "not_implemented") return `Asama ${stage}`;
  return "Bekliyor";
}

export function ComposeVerifyPage() {
  const [status, setStatus] = useState<IdentityStatus | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    try {
      setStatus(await fetchIdentity());
      setError(null);
    } catch (caught) {
      setError(toApiError(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card>
      <Card.Header>
        <Card.Title>Olustur ve Dogrula</Card.Title>
        <Card.Description>
          Ham metin, sweep farki, canonical bicim, imza, onay ve gonderim.
        </Card.Description>
      </Card.Header>

      <Card.Content className="flex flex-col gap-4">
        <Alert status="default">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Otomatik gonderim yoktur</Alert.Title>
            <Alert.Description>
              Her dis yazma islemi ayri ve tek kullanimlik bir kullanici onayi
              ister; imza onayi gonderim onayi degildir. Zamanlanmis mesaj,
              otomatik ping veya kendiliginden oda katilimi bu urunde bulunmaz.
            </Alert.Description>
          </Alert.Content>
        </Alert>

        <section aria-label="On kosullar" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">On kosullar</h3>

          {error !== null && (
            <ErrorRegion
              error={error}
              onRetry={() => void load()}
              retryPending={loading}
              section="Olustur ve Dogrula / On kosullar"
              title="Kapi durumu okunamadi"
            />
          )}

          {status === null && error === null && (
            <p className="text-sm text-muted">Kapi durumu okunuyor...</p>
          )}

          {status !== null && (
            <ul className="flex flex-col gap-2">
              {status.gate.checks.map((check) => (
                <li
                  key={check.key}
                  className="flex flex-col gap-1 rounded-lg border border-border p-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm font-medium text-foreground">
                      {gateReasonLabel(check.key)}
                    </span>
                    <StatusPill
                      label={labelFor(check.state, check.stage)}
                      tone={toneFor(check.state)}
                    />
                  </div>
                  <p className="text-xs text-muted">{check.detail}</p>
                </li>
              ))}
            </ul>
          )}
        </section>

        <Separator />

        {/* The composer reads its own capability from the backend rather than
            inferring one from the identity payload above: the gate it must
            obey is the one the three write steps re-run, not a copy of it.
            The identity read only answers whether signing will need the vault
            passphrase, which is a property of this machine's vault. */}
        {status !== null && (
          <ComposerPanel
            needsVaultPassphrase={status.identity?.protection === "dpapi+passphrase"}
          />
        )}

        <Alert status="default">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Uygunluk ile guncellik ayni sey degildir</Alert.Title>
            <Alert.Description>
              Uygunluk kontrolu, bu yapinin <strong>pinlenmis referans commit</strong>{" "}
              ile ayni davrandigini gosterir. Canli Technocore sunucusunun hala
              ayni protokolde oldugunu gostermez; onu resmi kaynak denetimi
              soyler ve denetim guncel degilse gonderim yolu kapali kalir.
            </Alert.Description>
          </Alert.Content>
        </Alert>
      </Card.Content>
    </Card>
  );
}
