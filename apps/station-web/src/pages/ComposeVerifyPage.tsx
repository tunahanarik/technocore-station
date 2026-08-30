import { Alert, Card, Separator } from "@heroui/react";

import { StatusPill } from "../components/StatusPill";

interface Prerequisite {
  readonly id: string;
  readonly title: string;
  readonly detail: string;
  readonly stage: string;
}

const PREREQUISITES: readonly Prerequisite[] = [
  {
    id: "identity",
    title: "Kimlik ve recovery",
    detail: "DID olusturulmus, DPAPI ile korunmus ve restore-test ile dogrulanmis olmali.",
    stage: "Asama 2",
  },
  {
    id: "conformance",
    title: "Uygunluk motoru",
    detail: "Sweep, canonical bicim, did:key ve imza resmi referansa karsi dogrulanmis olmali.",
    stage: "Asama 2B",
  },
  {
    id: "readonly",
    title: "Salt okunur Technocore",
    detail: "Resmi manifest okunmus ve protokol surukleme kontrolu kurulmus olmali.",
    stage: "Asama 3",
  },
];

/**
 * Compose & Verify, Stage 1: locked.
 *
 * The lock is real, not decorative. There is no text field and no send
 * control, because there is no signing path and no network client yet.
 */
export function ComposeVerifyPage() {
  return (
    <Card>
      <Card.Header>
        <Card.Title>Compose &amp; Verify</Card.Title>
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
              Kimlik ve uygunluk asamalari tamamlanmadan metin yazma, imzalama
              ve gonderme yollari acilmaz. Bu bilincli bir fail-closed
              davranistir: eksik bir uygunluk motoruyla imza uretmek,
              sunucunun sakladigi baytlarla eslesmeyen bir kayit olusturabilir.
            </Alert.Description>
          </Alert.Content>
        </Alert>

        <Separator />

        <section aria-label="On kosullar" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">On kosullar</h3>
          <ul className="flex flex-col gap-2">
            {PREREQUISITES.map((item) => (
              <li
                key={item.id}
                className="flex flex-col gap-1 rounded-lg border border-border p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium text-foreground">{item.title}</span>
                  <StatusPill label={`Bekliyor · ${item.stage}`} tone="pending" />
                </div>
                <p className="text-xs text-muted">{item.detail}</p>
              </li>
            ))}
          </ul>
        </section>

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
