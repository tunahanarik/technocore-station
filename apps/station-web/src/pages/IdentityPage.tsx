import { Alert, Card } from "@heroui/react";

import { EmptyState } from "../components/EmptyState";

/**
 * Identity surface, Stage 1.
 *
 * There is no identity, no seed field and no example DID here. A placeholder
 * that looked like a real identity would be worse than an empty state.
 */
export function IdentityPage() {
  return (
    <Card>
      <Card.Header>
        <Card.Title>Kimlik</Card.Title>
        <Card.Description>
          DID, koruma, recovery ve secret yasam dongusu bu yuzeyde yonetilir.
        </Card.Description>
      </Card.Header>

      <Card.Content className="flex flex-col gap-4">
        <EmptyState
          description="Bu bilgisayarda henuz bir Ed25519 did:key kimligi olusturulmadi ve iceri aktarilmadi. Kimlik olusturma Asama 2 ile gelir."
          title="Kimlik olusturulmadi"
        />

        <Alert status="default">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Secret bu bilgisayardan cikmaz</Alert.Title>
            <Alert.Description>
              Seed uretildiginde yalniz yerelde kalir ve Windows DPAPI ile
              korunur. Hicbir zaman arayuze, API yanitina, loga veya bir dil
              modeline gonderilmez. Bu ekranda bilerek hicbir secret giris
              alani yoktur.
            </Alert.Description>
          </Alert.Content>
        </Alert>

        <Alert status="warning">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Recovery dogrulanmadan yazma yapilamaz</Alert.Title>
            <Alert.Description>
              Sifreli bir recovery dosyasi uretilip restore-test ile
              dogrulanmadan hicbir Technocore yazma islemi acilmaz. Bu kural
              Asama 2 ile birlikte uygulanir.
            </Alert.Description>
          </Alert.Content>
        </Alert>
      </Card.Content>
    </Card>
  );
}
