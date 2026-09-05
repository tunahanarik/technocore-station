import { Alert, Card, Separator } from "@heroui/react";

import { EvidenceLedgerPanel } from "../components/evidence/EvidenceLedgerPanel";
import { ProofWorkspacePanel } from "../components/proof/ProofWorkspacePanel";

interface TrustLevel {
  readonly level: number;
  readonly name: string;
  readonly proves: string;
}

/**
 * Kanitlar: the evidence ledger, its four trust levels and the audit chain.
 *
 * The official-source panel used to live here; it moved to the Kaynaklar
 * section, because document access and protocol drift describe the remote
 * server, while this section records what this Station itself did.
 *
 * The list below is the *reference*: what each level would mean if a record
 * carried it. It is not a verdict about anything. Every real record states its
 * own four levels, one line each, inside the ledger panel - and level 4 is
 * absent in this release, on every record, stated rather than implied.
 */
const TRUST_LEVELS: readonly TrustLevel[] = [
  {
    level: 1,
    name: "Imza kaniti",
    proves:
      "DID ozel anahtarina sahip tarafin belirli canonical metni imzaladigi. Gercek kimligi veya zamani kanitlamaz.",
  },
  {
    level: 2,
    name: "Sunucu gozlemi",
    proves:
      "Station'in belirli bir sunucu yanitini gordugu. Sunucunun durustlugunu kanitlamaz.",
  },
  {
    level: 3,
    name: "Yerel kayit zamani",
    proves: "Yerel makinenin o anda gosterdigi saat. Guvenilir zaman damgasi degildir.",
  },
  {
    level: 4,
    name: "Harici anchor",
    proves: "MVP kapsaminda yoktur ve bos birakilir.",
  },
];

export function EvidencePage() {
  return (
    <Card>
      <Card.Header>
        <Card.Title>Kanitlar</Card.Title>
        <Card.Description>
          Kanit kayitlari, dort guven seviyesi, audit zinciri, disa aktarim ve
          bir gorevin kanit calisma alani. Buradaki hicbir sey bir sonuc
          degildir; toplanmis malzemedir.
        </Card.Description>
      </Card.Header>

      <Card.Content className="flex flex-col gap-4">
        <EvidenceLedgerPanel />

        <Separator />

        {/* Paket H3. No new section was opened for it: nine of nine sections
            are `ready: true` and `sections.ts` was not touched. The proof
            workspace belongs to Kanitlar, because what it shows is what this
            Station collected about one task (ADR-0009 9). */}
        <ProofWorkspacePanel />

        <Separator />

        <section aria-label="Guven seviyeleri" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">Guven seviyeleri</h3>
          <p className="text-xs text-muted">
            Asagidakiler seviyelerin tanimidir, bir kaydin durumu degildir. Her
            kayit hangi seviyenin dolu hangisinin bos oldugunu kendi tasir ve
            seviyeler tek bir rozete toplanmaz; seviyeler birbirinin yerine
            gecmez.
          </p>
          <ul className="flex flex-col gap-2">
            {TRUST_LEVELS.map((item) => (
              <li
                key={item.level}
                className="flex flex-col gap-1 rounded-lg border border-border p-3"
              >
                <span className="text-sm font-medium text-foreground">
                  {`Seviye ${String(item.level)}: ${item.name}`}
                </span>
                <p className="text-xs text-muted">{item.proves}</p>
              </li>
            ))}
          </ul>
        </section>

        <Alert status="default">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Kaynak siniflandirmasi</Alert.Title>
            <Alert.Description>
              Resmi belge, resmi sosyal aciklama ve topluluk iddiasi ayri ayri
              isaretlenir. Kaynagi olmayan bir iddia dogrulanmis sayilmaz ve bu
              urun hicbir airdrop garantisi, uygunluk skoru veya tahsis iddiasi
              uretmez.
            </Alert.Description>
          </Alert.Content>
        </Alert>
      </Card.Content>
    </Card>
  );
}
