import type { IdentityStatus } from "../api/types";
import type { StatusTone } from "../components/StatusPill";

/**
 * Shared identity presentation logic.
 *
 * Both the identity section and the overview summarise the same backend
 * state machine; deriving label, tone and "next safe step" in one module
 * keeps the two surfaces from ever disagreeing about what the state means.
 */

/**
 * Human wording for the gate check keys the backend reports.
 *
 * The same keys arrive in two places - `WriteGateStatus.checks` and the
 * composer capability's `blocking_reasons` - and both surfaces must call them
 * the same thing. An unknown key falls back to the raw key rather than being
 * dropped: a reason the UI cannot name is still a reason the user must see.
 */
export const GATE_REASON_LABELS: Readonly<Record<string, string>> = {
  identity_present: "Kimlik olusturulmus olmali",
  identity_not_revoked: "Kimlik revoke edilmemis olmali",
  vault_present: "Secret kasasi bulunmali",
  recovery_verified: "Recovery restore-test ile dogrulanmis olmali",
  conformance_verified: "Uygunluk motoru dogrulanmis olmali",
  manifest_current: "Resmi manifest kontrolu kurulmus olmali",
};

/** The label for one gate key, or the key itself when it is not catalogued. */
export function gateReasonLabel(key: string): string {
  return Object.hasOwn(GATE_REASON_LABELS, key) ? GATE_REASON_LABELS[key]! : key;
}

export function identityStateTone(status: IdentityStatus): StatusTone {
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

export function identityStateLabel(status: IdentityStatus): string {
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

/**
 * The single safest thing to do next.
 *
 * Derived from the backend's own gate checks rather than from a parallel copy
 * of the roadmap (IMP-233). Whatever the backend reports as blocking *is* the
 * next step, so this text cannot go stale when a stage ships.
 */
export function nextAction(status: IdentityStatus): string {
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
    case "revoked":
      return "Kimlik revoke edildi. Yeni bir kimlik olusturabilirsiniz.";
    case "ready":
      return readyNextAction(status);
  }
}

/** What a ready identity still needs, in the backend's own terms. */
function readyNextAction(status: IdentityStatus): string {
  const checks = new Map(status.gate.checks.map((check) => [check.key, check]));
  const conformance = checks.get("conformance_verified");
  const manifest = checks.get("manifest_current");

  if (conformance !== undefined && conformance.state !== "passed") {
    return "Uygunluk self-test'i gecmiyor. Asama 2B motorunu inceleyin.";
  }
  if (manifest !== undefined && manifest.state !== "passed") {
    return "Resmi kaynaklar bu oturumda henuz dogrulanmadi. Kaynaklar bolumunden 'Resmi kaynaklari denetle' calistirin.";
  }
  if (status.gate.allowed) {
    return "Butun on kosullar hazir. Asama 4 gonderim akisi 'Olustur ve Dogrula' bolumunde acik.";
  }
  return "Dis yazma icin eksik bir on kosul var. Ayrintilar asagidaki kapida.";
}
