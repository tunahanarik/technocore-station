import { Alert, Card, Separator } from "@heroui/react";
import { useCallback, useEffect, useState } from "react";

import { type ApiError, fetchWriteGate, toApiError } from "../api/client";
import type { AppStatus, WriteGateStatus } from "../api/types";
import { ErrorRegion } from "../components/ErrorRegion";
import { OpenCodeConnectionPanel } from "../components/opencode/OpenCodeConnectionPanel";
import { StatusPill } from "../components/StatusPill";
import { ThemeToggle } from "../components/ThemeToggle";

/**
 * Ayarlar ve Yardim: theme, application/service facts, the security gates
 * and honest notes about what is not built yet.
 *
 * The write-gate block reads the dedicated `/api/write-gate` endpoint - the
 * same evaluation the backend applies before any outward write - rather than
 * restating the roadmap in frontend copy.
 *
 * Paket G revised a promise this page used to make. It said, flatly, that
 * there was deliberately no secret input or display anywhere on this screen,
 * and a test held it there. That is no longer true: the OpenCode connection
 * panel below takes a provider API key. The sentence was rewritten rather
 * than deleted, and the test was **narrowed rather than dropped** - the page
 * may now contain exactly one masked field and it must be the provider key.
 * The exception is only ever the provider key: there is still no frontend
 * field, anywhere in this app, that accepts or shows a DID seed, a private
 * key or a recovery secret, and ADR-0001 6 authorised exactly this width and
 * no more.
 */

interface SettingsHelpPageProps {
  readonly status: AppStatus | null;
}

export function SettingsHelpPage({ status }: SettingsHelpPageProps) {
  const [gate, setGate] = useState<WriteGateStatus | null>(null);
  const [gateError, setGateError] = useState<ApiError | null>(null);
  const [gateLoading, setGateLoading] = useState(true);

  const load = useCallback(async (): Promise<void> => {
    setGateLoading(true);
    try {
      setGate(await fetchWriteGate());
      setGateError(null);
    } catch (caught) {
      setGate(null);
      setGateError(toApiError(caught));
    } finally {
      setGateLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <Card.Header>
          <Card.Title>Gorunum</Card.Title>
          <Card.Description>
            Tema tercihi bu oturum icindir. Tarayici deposu bu uygulamada
            kullanilmadigi icin secim kalici degildir; yeniden aciliste sistem
            temasi izlenir.
          </Card.Description>
        </Card.Header>
        <Card.Content>
          <ThemeToggle />
        </Card.Content>
      </Card>

      <Card>
        <Card.Header>
          <Card.Title>Uygulama ve servis</Card.Title>
          <Card.Description>Yerel servisin kendi bildirdigi durum.</Card.Description>
        </Card.Header>
        <Card.Content>
          {status === null ? (
            <p className="text-sm text-muted">
              Servis durumu okunamadi. Baglanti kurulunca burada servis asamasi,
              calisma modu ve veritabani bilgisi gorunur.
            </p>
          ) : (
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Servis asamasi</dt>
                <dd className="font-mono">{status.service.stage}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Calisma modu</dt>
                <dd>{status.service.mode === "production" ? "uretim" : "gelistirme"}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Veritabani</dt>
                <dd className="font-mono">
                  {`${status.database.state} · journal ${status.database.journal_mode} · surum ${status.database.schema_revision}`}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Oturum tasima</dt>
                <dd className="font-mono">{status.session_security.transport}</dd>
              </div>
            </dl>
          )}
        </Card.Content>
      </Card>

      <Card>
        <Card.Header>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Card.Title>Guvenlik kapilari</Card.Title>
            {gate !== null && (
              <StatusPill
                label={gate.allowed ? "Dis yazma acik" : "Dis yazma kapali"}
                tone={gate.allowed ? "ok" : "pending"}
              />
            )}
          </div>
          <Card.Description>
            Dis yazma kapisinin gercek durumu. Her kosul backend tarafindan
            degerlendirilir; bu liste onun okumasidir.
          </Card.Description>
        </Card.Header>
        <Card.Content className="flex flex-col gap-3">
          {gateError !== null && (
            <ErrorRegion
              error={gateError}
              onRetry={() => void load()}
              retryPending={gateLoading}
              section="Ayarlar ve Yardim / Guvenlik kapilari"
              title="Kapi durumu okunamadi"
            />
          )}
          {gate === null && gateError === null && (
            <p className="text-sm text-muted">Kapi durumu okunuyor...</p>
          )}
          {gate !== null && (
            <ul className="flex flex-col gap-1">
              {gate.checks.map((check) => (
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
          )}

          <Separator />

          <Alert status="default">
            <Alert.Indicator />
            <Alert.Content>
              <Alert.Title>Secret bu bilgisayardan cikmaz</Alert.Title>
              <Alert.Description>
                <span className="flex flex-col gap-2">
                  <span>
                    Seed yalniz yerelde kalir ve Windows DPAPI ile korunur.
                    Hicbir ayar bu davranisi degistiremez. DID seed&apos;i,
                    private key ve recovery parolasi icin frontend&apos;de
                    hicbir istisna yoktur: bunlari kabul eden veya gosteren bir
                    alan bu ekranda da, uygulamanin hicbir yerinde de
                    bulunmaz.
                  </span>
                  <span>
                    Tek istisna asagidaki OpenCode Go saglayici API
                    anahtaridir. Bu ekranin daha once verdigi &quot;hicbir
                    secret giris alani yoktur&quot; sozu bu paketle bilerek
                    daraltilarak yeniden yazildi: anahtar maskeli bir alana bir
                    kez yazilir, ayni-origin yerel servise bir kez iletilir,
                    kaydedildikten sonra alandan ve bellekten silinir ve hicbir
                    yoldan geri gosterilemez.
                  </span>
                </span>
              </Alert.Description>
            </Alert.Content>
          </Alert>
        </Card.Content>
      </Card>

      <OpenCodeConnectionPanel />

      <Card>
        <Card.Header>
          <Card.Title>Yardim</Card.Title>
        </Card.Header>
        <Card.Content>
          <p className="text-sm text-muted">
            OpenCode Go baglantisi Paket G&apos;de acildi. Kullanim kilavuzu
            artik yazildi ve depoda duruyor:{" "}
            <code>docs/kullanim-kilavuzu.md</code>; kabul listesi{" "}
            <code>docs/kullanici-kabul-listesi.md</code> dosyasindadir. Her
            bolum ayrica kendi aciklamasini tasir;
            sorun bildirirken hata kutusundaki &quot;Tani bilgisini
            kopyala&quot; ciktisini kullanin. O cikti bilerek redaktedir:
            yalnizca hata kodu, HTTP durumu, hata sinifi, istek kimligi, bolum
            adi ve zaman damgasi tasir - saglayici anahtari oraya hicbir
            kosulda girmez.
          </p>
        </Card.Content>
      </Card>
    </div>
  );
}
