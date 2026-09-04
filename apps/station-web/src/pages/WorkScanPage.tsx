import { WorkScanPanel } from "../components/workscan/WorkScanPanel";

/**
 * Is Tara: the read-only scan of public rooms the user chose.
 *
 * The page is a thin mount, like `EvidencePage` around its ledger: the whole
 * surface is one panel, because the flow - choose rooms, read them once, look
 * at what came back - is one decision the user makes in one place. Splitting
 * it across sub-panels would let a reader act on a candidate without the
 * honesty block that qualifies it, which is exactly the arrangement ADR-0007
 * 2 refuses.
 */
export function WorkScanPage() {
  return <WorkScanPanel />;
}
