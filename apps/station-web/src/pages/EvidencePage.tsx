import { Alert, Card, Separator } from "@heroui/react";

import { EmptyState } from "../components/EmptyState";
import { TechnocoreSourcesPanel } from "../components/TechnocoreSourcesPanel";

interface TrustLevel {
  readonly level: number;
  readonly name: string;
  readonly proves: string;
}

/**
 * The four trust levels, stated with their limits. Level 4 is empty in the
 * MVP and is shown as absent rather than implied.
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
        <Card.Title>Evidence &amp; Sources</Card.Title>
        <Card.Description>
          Kanit kayitlari, guven seviyeleri ve resmi kaynak suruklenmesi.
        </Card.Description>
      </Card.Header>

      <Card.Content className="flex flex-col gap-4">
        <TechnocoreSourcesPanel />

        <Separator />

        <EmptyState
          description="Bu bilgisayarda henuz hicbir kanit kaydi yok. Kayitlar ancak kullanici onayli bir gonderim yapildiktan sonra olusur; gonderim yolu Asama 4 ile acilir."
          title="Henuz kanit kaydi yok"
        />

        <Separator />

        <section aria-label="Guven seviyeleri" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">Guven seviyeleri</h3>
          <p className="text-xs text-muted">
            Bir kayit olustugunda hangi seviyenin dolu, hangisinin bos oldugu
            acikca gosterilir. Seviyeler birbirinin yerine gecmez.
          </p>
          <ul className="flex flex-col gap-2">
            {TRUST_LEVELS.map((item) => (
              <li
                key={item.level}
                className="flex flex-col gap-1 rounded-lg border border-border p-3"
              >
                <span className="text-sm font-medium text-foreground">
                  {`Seviye ${item.level} · ${item.name}`}
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
