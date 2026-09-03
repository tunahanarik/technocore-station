import { Alert, Card, Separator } from "@heroui/react";
import { useCallback, useEffect, useState } from "react";

import { type ApiError, fetchIdentity, toApiError } from "../api/client";
import type { IdentityStatus } from "../api/types";
import { ErrorRegion } from "../components/ErrorRegion";
import { StatusPill, type StatusTone } from "../components/StatusPill";

/**
 * Compose & Verify, Stage 2B: still locked, and still locked by the *real*
 * write gate rather than by a hardcoded list.
 *
 * Stage 2B built the canonicalization engine, so that half of the lock has
 * lifted. The surface stays closed anyway, and deliberately: there is no
 * network client, and nothing yet detects the live server drifting off the
 * pinned protocol. There is no text field and no send control, because
 * signing without drift detection would produce a record that cannot be
 * re-verified against the bytes the server stores.
 */

const STAGE_LABELS: Record<string, string> = {
  identity_present: "Kimlik olusturulmus olmali",
  identity_not_revoked: "Kimlik revoke edilmemis olmali",
  vault_present: "Secret kasasi bulunmali",
  recovery_verified: "Recovery restore-test ile dogrulanmis olmali",
  conformance_verified: "Uygunluk motoru dogrulanmis olmali",
  manifest_current: "Resmi manifest kontrolu kurulmus olmali",
};

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
        <Alert status="warning">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Bu yuzey kilitli</Alert.Title>
            <Alert.Description>
              Kimlik, recovery ve uygunluk asamalari tamamlanmadan metin yazma,
              imzalama ve gonderme yollari acilmaz. Bu bilincli bir fail-closed
              davranistir: dogrulanmamis bir uygunluk motoruyla imza uretmek,
              sunucunun sakladigi baytlarla eslesmeyen bir kayit olusturabilir.
              Uygunluk self-test'i basarisiz olursa bu yuzey yine kilitli kalir.
            </Alert.Description>
          </Alert.Content>
        </Alert>

        <Separator />

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
                      {STAGE_LABELS[check.key] ?? check.key}
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

        <Alert status="default">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Uygunluk ile guncellik ayni sey degildir</Alert.Title>
            <Alert.Description>
              Uygunluk kontrolu, bu yapinin <strong>pinlenmis referans commit</strong>{" "}
              ile ayni davrandigini gosterir. Canli Technocore sunucusunun hala
              ayni protokolde oldugunu gostermez. Manifest surukleme kontrolu
              Asama 3'te gelir ve o gelene kadar dis yazma kapisi kapali kalir.
            </Alert.Description>
          </Alert.Content>
        </Alert>

        <Alert status="default">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Otomatik gonderim yoktur</Alert.Title>
            <Alert.Description>
              Acildiginda bile her dis yazma islemi ayri ve tek kullanimlik bir
              kullanici onayi ister. Zamanlanmis mesaj, otomatik ping veya
              kendiliginden oda katilimi bu urunde bulunmaz.
            </Alert.Description>
          </Alert.Content>
        </Alert>
      </Card.Content>
    </Card>
  );
}
