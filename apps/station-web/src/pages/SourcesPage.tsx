import { Card } from "@heroui/react";

import { TechnocoreSourcesPanel } from "../components/TechnocoreSourcesPanel";

/**
 * Kaynaklar: the read-only official-source surface.
 *
 * Document access, the protocol evaluation and the critical diff *are* this
 * section - that is why the panel lives here rather than next to the
 * evidence ledger, which records what this Station itself did.
 */
export function SourcesPage() {
  return (
    <Card>
      <Card.Header>
        <Card.Title>Kaynaklar</Card.Title>
        <Card.Description>
          Resmi belge erisimi, protokol degerlendirmesi ve kritik fark.
        </Card.Description>
      </Card.Header>
      <Card.Content className="flex flex-col gap-4">
        <TechnocoreSourcesPanel />
      </Card.Content>
    </Card>
  );
}
