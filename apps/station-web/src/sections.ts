/**
 * The dashboard's section registry - the one place that knows which sections
 * exist, what each is for, and which are actually built.
 *
 * The left navigation renders **only** entries with `ready: true`. The rest
 * are registered here so the target layout (ADR-0001 item 2: nine sections)
 * stays visible in code review, but they never reach the DOM: an empty
 * section pretending to be a feature is exactly what this app refuses to
 * show. When the package named in the comment lands, its entry flips to
 * `ready: true` and nothing else has to change.
 *
 * There is deliberately no router and no URL sync: deep links are out of
 * scope (no new dependency), selection is plain React state, and a reload
 * returns to the first section.
 */

export type SectionId =
  | "overview"
  | "work-scan"
  | "tasks"
  | "activity"
  | "identity"
  | "compose"
  | "sources"
  | "evidence"
  | "settings";

export interface SectionDefinition {
  readonly id: SectionId;
  /** Visible navigation label. Diacritic-free Turkish, like all UI text. */
  readonly label: string;
  /** What the section is for - documentation and future tooltips. */
  readonly purpose: string;
  /** Only ready sections are rendered in the navigation. */
  readonly ready: boolean;
}

export const SECTIONS: readonly SectionDefinition[] = [
  {
    id: "overview",
    label: "Genel Bakis",
    purpose: "Kimlik, Technocore, uygunluk ve servis sagliginin tek bakislik ozeti.",
    ready: true,
  },
  {
    // Paket H1 (Work Scan) ile acildi (ADR-0007 9). Kullanicinin sectigi acik
    // odalar bir kez okunur; zamanlayici, arka plan gorevi ve otomatik
    // yenileme yoktur ve butun oda evreni hicbir zaman taranmaz.
    id: "work-scan",
    label: "Is Tara",
    purpose:
      "Kullanicinin sectigi acik odalarin salt okunur, tek seferlik taramasi ve kural tabanli aday cikarimi.",
    ready: true,
  },
  {
    // Paket F / H2 (gorev modulu + agent calisma ortami) ile acilir.
    id: "tasks",
    label: "Gorevler",
    purpose: "Kullanicinin baslattigi sinirli gorevlerin listesi ve durumu.",
    ready: false,
  },
  {
    // Paket H2 (Activity Desk) ile acilir.
    id: "activity",
    label: "Aktivite",
    purpose: "Agent calisma ortaminin adim adim aktivite kaydi.",
    ready: false,
  },
  {
    id: "identity",
    label: "Kimlik ve Guvenlik",
    purpose: "DID, koruma, recovery ve secret yasam dongusu.",
    ready: true,
  },
  {
    id: "compose",
    label: "Olustur ve Dogrula",
    purpose: "Metin, sweep farki, canonical bicim, imza, onay ve gonderim.",
    ready: true,
  },
  {
    id: "sources",
    label: "Kaynaklar",
    purpose: "Resmi belge erisimi, protokol degerlendirmesi ve kritik fark.",
    ready: true,
  },
  {
    id: "evidence",
    label: "Kanitlar",
    purpose: "Kanit kayitlari ve dort guven seviyesi.",
    ready: true,
  },
  {
    id: "settings",
    label: "Ayarlar ve Yardim",
    purpose: "Tema, uygulama bilgisi, guvenlik kapilari ve yardim notlari.",
    ready: true,
  },
];

/** What the navigation actually shows. */
export const READY_SECTIONS: readonly SectionDefinition[] = SECTIONS.filter(
  (section) => section.ready,
);

/** The section selected on launch. */
export const DEFAULT_SECTION_ID: SectionId = "overview";
