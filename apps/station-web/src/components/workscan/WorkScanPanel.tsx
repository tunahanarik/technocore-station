import { Alert, Button, Card, Checkbox, Separator } from "@heroui/react";
import { useCallback, useEffect, useId, useState } from "react";

import {
  type ApiError,
  WORK_SCAN_MAX_ROOMS,
  fetchWorkScanStatus,
  refreshWorkScanDiscovery,
  refreshWorkScanRooms,
  scanWorkRooms,
  suggestWorkScanCandidate,
  toApiError,
} from "../../api/client";
import type {
  WorkScanAdapter,
  WorkScanAdapterFact,
  WorkScanAnnouncedRoom,
  WorkScanCandidate,
  WorkScanDiscovery,
  WorkScanResult,
  WorkScanRoom,
  WorkScanRoomIndex,
  WorkScanStaleness,
  WorkScanStatus,
  WorkScanSuggestion,
  WorkScanUntrusted,
} from "../../api/types";
import { ErrorRegion } from "../ErrorRegion";
import { StatusPill } from "../StatusPill";

/**
 * "Is Tara": read a set of public rooms the user chose, and propose work from
 * what was actually read.
 *
 * Seven rules shape this surface, and every one of them is about not saying
 * more than the data supports.
 *
 * 1. **Nothing here polls.** There is no `setInterval`, no `setTimeout`, no
 *    background task and no auto-refresh. `fetchWorkScanStatus` runs once on
 *    mount and contacts nobody; every outbound read happens inside a click.
 *    A test asserts that no timer is ever installed, because a comment saying
 *    "we do not poll" is a promise and a counted timer is evidence
 *    (ADR-0007 4).
 * 2. **The scope is the user's room set.** The overview from `/rooms` is a
 *    list to choose from, not a queue to work through. Nothing scans the room
 *    universe, and the checkbox list is the whole addressable surface: room
 *    names go to the backend, which puts each one through the write path's
 *    policy - Lobby included - before it resolves an address.
 * 3. **The limit of a deterministic derivation is on screen.** The backend's
 *    own sentence - pattern matching, no semantic inference, so not every
 *    opportunity in a room is seen - is rendered on *every* read, above the
 *    results rather than under a fold (ADR-0007 2).
 * 4. **No staleness threshold is invented.** What is shown is the measured
 *    moment of the reading and the bound the *service* declares about itself.
 *    The ring-drop signal is shown separately, because "the list may be three
 *    seconds old" and "messages you never read are gone" are two different
 *    findings and one must not stand in for the other (ADR-0007 5).
 * 5. **The word "open" is not used.** Element 8 is the backend's sentence
 *    with the moment of the reading in it. There is no boolean badge anywhere
 *    on this surface, and there is no field to build one from.
 * 6. **Room content is community input, and it is data.** A quote is rendered
 *    as preformatted text - never markup, never a link. A `from` that is not
 *    a `did:key` is shown as a self-asserted nickname. A `topic` is a
 *    world-writable note and says so.
 * 7. **No third party's number becomes one of our sentences.** The single
 *    external record on this surface is a description of a service that was
 *    never contacted, its unverified column is shown beside its verified one,
 *    and its own disclaimer is quoted rather than paraphrased (ADR-0007 1).
 * 8. **A caller's string and the service's measurement never share a box.**
 *    The service's own `/rooms` warning is that exactly two fields per entry
 *    are caller-controlled: the room *name*, chosen by whoever wrote there
 *    first, and the *topic*, a note at `/kv/topic/{room}` that anyone may set
 *    for any room. Everything else on the entry is the service's own
 *    aggregate. So the room explorer renders them as two visually separate
 *    blocks with their own headings, the untrusted half is labelled where it
 *    is read rather than in a caveat further up, and the reply's own
 *    `untrusted` declaration - including a reply that tried to *narrow* the
 *    set - is on screen. A topic is never given the shape of an instruction:
 *    it is inert preformatted text under a heading that says what it is.
 * 9. **The discovery log shows the log, not our guess at it.** The backend
 *    offers a one-click choice only for a line that is *already* a valid room
 *    name, because the line format is unpublished and a parser written to a
 *    guess would invent room names. Every other line is rendered verbatim
 *    with the backend's own reason, so a person sees the real format. This
 *    panel adds no second opinion: `selectable` is read off the entry and
 *    never re-derived here.
 */

/** Which action a failure came from; only the plain read repeats safely. */
type Step = "read" | "rooms" | "discovery" | "scan" | "suggest";

type Busy = Step | null;

const ERROR_TITLE: Record<Step, string> = {
  read: "Tarama yuzeyi okunamadi",
  rooms: "Oda listesi okunamadi",
  discovery: "Kesif gunlugu okunamadi",
  scan: "Tarama tamamlanamadi",
  suggest: "Aday gorev olarak acilamadi",
};

/**
 * The four signals the backend recognises, in the user's language.
 *
 * A lookup with a fallback rather than an exhaustive `Record`: `signal`
 * arrives as a plain string, and a value this table does not know is shown as
 * it came rather than dropped or renamed into the nearest match.
 */
const SIGNAL_LABEL: Record<string, string> = {
  help_wanted: "yardim cagrisi",
  defect_report: "hata bildirimi",
  review_request: "inceleme istegi",
  documentation_gap: "belge eksigi",
};

/** How far an external service was taken. Never "supported": none is. */
const SUPPORT_LABEL: Record<string, string> = {
  support_unverified: "Destek dogrulanamadi",
  declined: "Incelendi ve elendi",
  unexamined: "Henuz incelenmedi",
};

function formatDate(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("tr-TR");
}

/**
 * The staleness line that goes with a snapshot the service declared a bound
 * for.
 *
 * Rendered unconditionally, never behind a condition: a note that only
 * appeared when something looked wrong would be a note nobody ever reads, and
 * there is no threshold here that could decide when to show it.
 */
function StalenessLine({
  staleness,
  testId,
}: {
  readonly staleness: WorkScanStaleness;
  readonly testId: string;
}) {
  return (
    <p className="text-xs text-muted" data-testid={testId}>
      {`${staleness.detail} Olculen okuma ani: ${formatDate(staleness.read_at)}. Sunucunun kendi beyani: ${String(
        staleness.declared_cache_seconds,
      )} saniye (kaynak: ${staleness.declared_by}).`}
    </p>
  );
}

/** One verified/unverified fact row. The state travels with the sentence. */
function FactList({ facts, label }: { readonly facts: readonly WorkScanAdapterFact[]; readonly label: string }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-xs font-medium text-foreground">
        {`${label} (${String(facts.length)})`}
      </p>
      <ul className="flex flex-col gap-1">
        {facts.map((fact) => (
          <li className="text-xs text-muted" key={fact.key}>
            {`• ${fact.key}: ${fact.detail}`}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * The external service record.
 *
 * Two columns and both of them shown. A record that listed only what worked
 * would be the "reporting an absence as full support" failure the charter
 * names, and the unverified column is the entire reason no adapter exists.
 */
function AdapterRecord({ adapter }: { readonly adapter: WorkScanAdapter }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-foreground">{adapter.name}</span>
        <StatusPill label={SUPPORT_LABEL[adapter.support] ?? adapter.support} tone="pending" />
        {/* `adapter_written` and `contacted` are `false` as types, so these
            two pills have no branch behind them and cannot drift. */}
        <StatusPill label="Adapter yazilmadi" tone="inactive" />
        <StatusPill label="Hicbir istek gonderilmedi" tone="inactive" />
      </div>

      <p className="font-mono text-xs text-muted">
        {`Beyan edilen kaynak: ${adapter.declared_origin} · otorite seviyesi ${String(adapter.authority)} (topluluk)`}
      </p>

      <FactList facts={adapter.verified} label="Dogrulanan" />
      <FactList facts={adapter.unverified} label="Dogrulanamayan" />

      {/* The service's own words, quoted. Preformatted and unlinked like every
          other piece of foreign text on this surface. */}
      <blockquote className="flex flex-col gap-1 border-l-2 border-border pl-3">
        <pre className="whitespace-pre-wrap break-words font-mono text-xs text-foreground">
          {adapter.self_description_source}
        </pre>
        <pre className="whitespace-pre-wrap break-words font-mono text-xs text-foreground">
          {adapter.score_self_description}
        </pre>
        <span className="text-xs text-muted">
          Servisin kendi ifadeleri, yazildigi dilde. Asagidaki Turkce cumle
          yerel servisten geldigi gibi gosterilir.
        </span>
      </blockquote>

      <p className="text-xs text-muted">{adapter.self_description}</p>
      <p className="text-xs text-muted" data-testid="workscan-score-caveat">
        {adapter.score_caveat}
      </p>
      <p className="text-xs text-muted" data-testid="workscan-adapter-provenance">
        {adapter.provenance}
      </p>
    </div>
  );
}

/**
 * One candidate, with all eight elements on screen.
 *
 * Nothing is collapsed and nothing is omitted. The backend cannot produce a
 * candidate that is missing one of these, and a UI that hid one would undo
 * that guarantee at the last step: the elements a reader would skip - the
 * risks, the permissions, the estimate's basis - are exactly the ones that
 * decide whether accepting the suggestion is a good idea.
 */
function CandidateCard({
  candidate,
  disabled,
  groupName,
  onChoose,
  selected,
}: {
  readonly candidate: WorkScanCandidate;
  readonly disabled: boolean;
  readonly groupName: string;
  readonly onChoose: (id: string) => void;
  readonly selected: boolean;
}) {
  const { capability, effort, open_state: openState, source } = candidate;

  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2">
          <input
            checked={selected}
            disabled={disabled}
            name={groupName}
            onChange={() => onChoose(candidate.id)}
            type="radio"
            value={candidate.id}
          />
          <span className="text-sm font-medium text-foreground">
            {`Aday: ${SIGNAL_LABEL[candidate.signal] ?? candidate.signal}`}
          </span>
        </label>
        <StatusPill label="Topluluk icerigi (seviye 3)" tone="pending" />
      </div>

      <section aria-label={`1. Birebir alinti - ${source.reference}`} className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">1. Birebir alinti ve kaynak</h4>
        {/* Data, not markup and not a link. `pre` keeps it verbatim, and there
            is no anchor, no auto-linking and no `dangerouslySetInnerHTML`
            anywhere on this surface (SI-54). */}
        <pre
          className="whitespace-pre-wrap break-words rounded-lg bg-surface-secondary p-2 font-mono text-xs text-foreground"
          data-testid="workscan-quote"
        >
          {source.quote}
        </pre>
        <p className="font-mono text-xs text-muted">
          {`Kaynak: ${source.reference} · oda ${source.room} · sira ${String(source.seq)} · zaman ${source.ts}`}
        </p>
        <p className="font-mono text-xs text-muted">
          {`Yazar: ${source.author === "" ? "(bos)" : source.author} · ${
            source.author_is_did_key ? "did:key kalibina uyuyor" : "kendi beyan ettigi takma ad"
          }`}
        </p>
        <p className="text-xs text-muted">{source.author_detail}</p>
      </section>

      <section aria-label="2. Kime faydasi var" className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">2. Kime faydasi var</h4>
        <p className="text-xs text-muted">{candidate.benefit}</p>
      </section>

      <section aria-label="3. Teslimat" className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">3. Teslimat</h4>
        <p className="text-xs text-muted">{candidate.deliverable}</p>
      </section>

      <section aria-label="4. Basari kosulu ve testi" className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">4. Basari kosulu ve nasil test edilecegi</h4>
        <p className="text-xs text-muted">{candidate.success_condition}</p>
        <p className="text-xs text-muted">{candidate.test_method}</p>
      </section>

      <section aria-label="5. Arac ve veri yetkinligi" className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">
          5. Agent bu ise yetecek araca ve veriye sahip mi
        </h4>
        <p className="text-xs text-muted">{capability.detail}</p>
        <p className="font-mono text-xs text-muted">
          {`Modul: ${capability.module_id} (${capability.module_state}) · modul var: ${
            capability.module_available ? "evet" : "hayir"
          } · yazma kapisi: ${capability.write_gate_open ? "acik" : "kapali"} · ikisi birden: ${
            capability.ready ? "evet" : "hayir"
          }`}
        </p>
      </section>

      <section aria-label="6. Calisma tahmini ve butce" className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">6. Calisma tahmini ve butce</h4>
        <p className="text-xs text-muted" data-testid="workscan-effort">
          {`Bu bir ${effort.label}tir, olcum degildir: ${effort.band}.`}
        </p>
        <p className="text-xs text-muted">{effort.basis}</p>
        <p className="text-xs text-muted" data-testid="workscan-budget">
          {`Butce durumu: ${candidate.budget_state}. ${candidate.budget_detail}`}
        </p>
      </section>

      <section aria-label="7. Izinler ve riskler" className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">7. Gereken izinler ve riskler</h4>
        <ul className="flex flex-col gap-1">
          {candidate.permissions.map((permission) => (
            <li className="text-xs text-muted" key={permission}>{`• Izin: ${permission}`}</li>
          ))}
          {candidate.risks.map((risk) => (
            <li className="text-xs text-muted" key={risk}>{`• Risk: ${risk}`}</li>
          ))}
        </ul>
      </section>

      <section aria-label="8. Aciklik notu" className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">8. Isin durumu hakkinda soylenebilecek</h4>
        {/* The one permitted wording, rendered as it arrives. There is no
            badge here and no boolean to build one from. */}
        <p className="text-xs text-muted" data-testid="workscan-open-state">
          {openState.detail}
        </p>
        <p className="font-mono text-xs text-muted">
          {`Anlik goruntunun okundugu an: ${formatDate(openState.read_at)}`}
        </p>
      </section>

      <p className="font-mono text-xs text-muted">
        {`Uretim yontemi: ${candidate.derivation} · aday kimligi: ${candidate.id.slice(0, 12)}`}
      </p>
    </li>
  );
}

/**
 * The heading that opens the caller-written half of any listing entry.
 *
 * One component so the wording cannot drift between the room list and the
 * discovery log, and so "the untrusted half is labelled" is a single thing to
 * change rather than a habit each block is trusted to keep.
 */
function UntrustedHeading({ children, testId }: {
  readonly children: string;
  readonly testId?: string;
}) {
  return (
    <p
      className="text-xs font-semibold uppercase tracking-wide text-warning"
      data-testid={testId}
    >
      {children}
    </p>
  );
}

/**
 * What the reply said about its own caller-written fields.
 *
 * Both lists travel and so do both disagreements, because they are different
 * events: `extra_fields` is a reply *widening* the untrusted set, which this
 * build accepts, and `missing_fields` is a reply *narrowing* it, which this
 * build refuses. Showing only the union would hide which side moved, and
 * showing only our own list would make the screen silent about an attempt to
 * shrink it. `present: false` is its own answer too - "no declaration" is not
 * "a declaration that omits our fields".
 */
function UntrustedDeclaration({ untrusted }: { readonly untrusted: WorkScanUntrusted }) {
  const union = [...new Set([...untrusted.build_fields, ...untrusted.fields])].sort();

  return (
    <div
      className="flex flex-col gap-1 rounded-lg border border-warning/40 p-2"
      data-testid="workscan-untrusted"
    >
      <UntrustedHeading>Cagiranin yazdigi alanlar (untrusted)</UntrustedHeading>
      <p className="text-xs text-muted">{untrusted.detail}</p>
      <p className="font-mono text-xs text-muted">
        {`Yanitin kendi bildirimi: ${untrusted.present ? "var" : "yok"} · yanitin saydigi: ${
          untrusted.fields.length === 0 ? "(hicbiri)" : untrusted.fields.join(", ")
        } · Station'in saydigi: ${untrusted.build_fields.join(", ")} · gecerli kume (birlesim): ${union.join(
          ", ",
        )}`}
      </p>
      <p className="font-mono text-xs text-muted" data-testid="workscan-untrusted-drift">
        {`Yanitin ekledigi: ${
          untrusted.extra_fields.length === 0 ? "(yok)" : untrusted.extra_fields.join(", ")
        } · yanitin saymadigi: ${
          untrusted.missing_fields.length === 0 ? "(yok)" : untrusted.missing_fields.join(", ")
        }`}
      </p>
      {untrusted.note !== "" && (
        <pre className="whitespace-pre-wrap break-words font-mono text-xs text-muted">
          {untrusted.note}
        </pre>
      )}
      <p className="text-xs text-muted">
        Bir yanit bu kumeyi genisletebilir, daraltamaz. Yukarida
        &quot;saymadigi&quot; diye listelenen bir alan yine de cagiran yazimi
        sayilir.
      </p>
    </div>
  );
}

/**
 * One listing entry, with its two halves in two boxes.
 *
 * This is the shape the service's own warning asks for. `/rooms` says that
 * exactly two fields per entry are caller-controlled - the room name, chosen
 * by whoever wrote there first, and the topic, a note at `/kv/topic/{room}`
 * that anyone may set for *any* room - and that everything else is the
 * service's own measurement. Rendering the two in one block with a caveat
 * underneath would leave a reader to remember which was which; rendering them
 * in two boxes with their own headings means they cannot be confused by
 * skimming, which is how they will be read.
 *
 * The topic is inert preformatted text under a heading naming it as a
 * stranger's note. It is never given the shape of an instruction, a
 * description or a label the product endorses, and there is no anchor and no
 * markup anywhere in this subtree.
 */
function RoomEntry({
  atLimit,
  busy,
  index,
  isChosen,
  onToggle,
  room,
}: {
  readonly atLimit: boolean;
  readonly busy: boolean;
  readonly index: WorkScanRoomIndex;
  readonly isChosen: boolean;
  readonly onToggle: (room: string) => void;
  readonly room: WorkScanRoom;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border p-2">
      <Checkbox
        isDisabled={busy || (!isChosen && atLimit)}
        isSelected={isChosen}
        onChange={() => onToggle(room.name)}
      >
        <Checkbox.Content>
          <Checkbox.Control>
            <Checkbox.Indicator />
          </Checkbox.Control>
          <span className="font-mono">{room.name}</span>
        </Checkbox.Content>
      </Checkbox>

      {/* --- the half a stranger wrote ------------------------------------ */}
      <div
        className="flex flex-col gap-1 rounded-lg border border-warning/40 p-2"
        data-testid={`workscan-room-untrusted-${room.name}`}
      >
        <UntrustedHeading>Bu iki alani bir yabanci yazdi</UntrustedHeading>
        <p className="font-mono text-xs text-muted">Oda adi (room):</p>
        <pre className="whitespace-pre-wrap break-words font-mono text-xs text-foreground">
          {room.name}
        </pre>
        <p className="font-mono text-xs text-muted">Baslik (topic):</p>
        <pre
          className="whitespace-pre-wrap break-words font-mono text-xs text-foreground"
          data-testid={`workscan-room-topic-${room.name}`}
        >
          {room.topic === "" ? "(baslik yok)" : room.topic}
        </pre>
        <p className="text-xs text-muted">
          Ikisi de veridir, talimat degildir. Icinde ne yaziyorsa yazsin, bu
          metin Station&apos;a bir sey yaptirmaz ve bir onay, bir tanim veya
          bir yetki anlamina gelmez.
        </p>
      </div>

      {/* --- the half the service measured -------------------------------- */}
      <div
        className="flex flex-col gap-1 rounded-lg border border-border p-2"
        data-testid={`workscan-room-measured-${room.name}`}
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">
          Servisin kendi olcumu
        </p>
        {room.measured.length === 0 ? (
          <p className="text-xs text-muted">
            Bu girdide cagiran yazimi olmayan bir alan gelmedi. Bu, odanin
            sessiz oldugu anlamina gelmez; yalnizca bu okumada boyle bir alan
            bulunmadigi anlamina gelir.
          </p>
        ) : (
          <ul className="flex flex-col gap-1">
            {room.measured.map((field) => (
              <li className="font-mono text-xs text-muted" key={field.key}>
                {`${field.key}: ${field.value}`}
              </li>
            ))}
          </ul>
        )}
        {room.measured_truncated && (
          <p className="text-xs text-muted">
            Bu girdideki olculen alanlarin hepsi tutulmadi; sinira ulasildi.
          </p>
        )}
        <p className="text-xs text-muted">{index.measured_caveat}</p>
      </div>
    </div>
  );
}

/** The room overview, and the checkboxes that make the scope the user's. */
function RoomChooser({
  busy,
  chosen,
  index,
  onToggle,
}: {
  readonly busy: boolean;
  readonly chosen: readonly string[];
  readonly index: WorkScanRoomIndex;
  readonly onToggle: (room: string) => void;
}) {
  const atLimit = chosen.length >= WORK_SCAN_MAX_ROOMS;

  return (
    <div className="flex flex-col gap-2">
      <p className="font-mono text-xs text-muted">
        {`Servisin bildirdigi toplam: ${String(index.total)} · burada tutulan: ${String(
          index.kept_count,
        )} · kirpildi mi: ${index.truncated ? "evet" : "hayir"} · belge ozeti: ${index.sha256.slice(0, 12)}`}
      </p>
      <StalenessLine staleness={index.staleness} testId="workscan-staleness-rooms" />
      <p className="text-xs text-muted">{index.room_name_caveat}</p>
      <p className="text-xs text-muted" data-testid="workscan-topic-caveat">
        {`${index.topic_caveat} Bir baslik bir onay degildir ve odanin ne oldugunu kanitlamaz.`}
      </p>
      {/* Unconditional: an unlisted room is never enumerated here, so the
          list's silence about one is not evidence that it is absent. */}
      <p className="text-xs text-muted" data-testid="workscan-unlisted-note">
        {index.unlisted_note}
      </p>

      <UntrustedDeclaration untrusted={index.untrusted} />

      {index.rooms.length === 0 ? (
        <p className="text-sm text-muted">
          Listede oda yok. Bu, taranacak bir sey olmadigi anlamina gelmez;
          yalnizca bu okumada oda listelenmedigi anlamina gelir.
        </p>
      ) : (
        <fieldset className="flex max-h-96 flex-col gap-2 overflow-y-auto">
          <legend className="text-sm font-medium text-foreground">
            {`Taranacak odalar (secili: ${String(chosen.length)} / en cok ${String(WORK_SCAN_MAX_ROOMS)})`}
          </legend>
          {index.rooms.map((room) => (
            <RoomEntry
              atLimit={atLimit}
              busy={busy}
              index={index}
              isChosen={chosen.includes(room.name)}
              key={room.name}
              onToggle={onToggle}
              room={room}
            />
          ))}
        </fieldset>
      )}

      {atLimit && (
        <p className="text-xs text-muted">
          {`Tek bir taramada en cok ${String(
            WORK_SCAN_MAX_ROOMS,
          )} oda okunur. Kalan odalari ayri bir taramayla secebilirsiniz.`}
        </p>
      )}
    </div>
  );
}

/**
 * One line of the discovery log.
 *
 * The split here is the backend's, not this component's: `selectable` arrives
 * on the entry and is never re-derived. A line that is already a valid room
 * name gets a checkbox; every other line is shown **as it arrived**, with the
 * backend's own reason beside it, because the log's line format is not
 * published and the raw line is the only evidence a person has of what the
 * real format is. A parser written to a guess would produce room names this
 * product invented, and a made-up name that happens to validate would be a
 * one-click scan target for a room nobody announced.
 *
 * One line arrives with its text dropped: a line announcing a room this
 * product never names. Repeating it would be how that name reached a screen
 * through the very check that exists to keep it off one, so the reason is
 * shown and the text is not.
 */
function DiscoveryEntry({
  atLimit,
  busy,
  entry,
  isChosen,
  onToggle,
}: {
  readonly atLimit: boolean;
  readonly busy: boolean;
  readonly entry: WorkScanAnnouncedRoom;
  readonly isChosen: boolean;
  readonly onToggle: (room: string) => void;
}) {
  return (
    <li className="flex flex-col gap-1 rounded-lg border border-border p-2">
      <p className="font-mono text-xs text-muted">
        {`sira ${String(entry.seq)} · zaman ${entry.ts}`}
      </p>

      {entry.selectable ? (
        <>
          <Checkbox
            isDisabled={busy || (!isChosen && atLimit)}
            isSelected={isChosen}
            onChange={() => onToggle(entry.name)}
          >
            <Checkbox.Content>
              <Checkbox.Control>
                <Checkbox.Indicator />
              </Checkbox.Control>
              <span className="font-mono">{entry.name}</span>
            </Checkbox.Content>
          </Checkbox>
          <UntrustedHeading>Duyurulan oda adini bir yabanci yazdi</UntrustedHeading>
          <p className="text-xs text-muted">
            Bir satirin burada olmasi o odanin duyuruldugunu soyler; odanin ne
            oldugunu, kimin oldugunu veya guvenilir oldugunu soylemez.
          </p>
        </>
      ) : (
        <>
          <p className="font-mono text-xs text-muted">Satir, geldigi gibi:</p>
          {entry.line === "" ? (
            <p className="text-xs text-muted" data-testid={`workscan-discovery-dropped-${String(entry.seq)}`}>
              Bu satirin metni gosterilmiyor.
            </p>
          ) : (
            <pre
              className="whitespace-pre-wrap break-words rounded-lg bg-surface-secondary p-2 font-mono text-xs text-foreground"
              data-testid={`workscan-discovery-line-${String(entry.seq)}`}
            >
              {entry.line}
            </pre>
          )}
          <p
            className="text-xs text-muted"
            data-testid={`workscan-discovery-reason-${String(entry.seq)}`}
          >
            {entry.unusable_reason}
          </p>
        </>
      )}
    </li>
  );
}

/** One read of the discovery log: what was announced, and what could not be read. */
function DiscoveryLog({
  busy,
  chosen,
  discovery,
  onToggle,
}: {
  readonly busy: boolean;
  readonly chosen: readonly string[];
  readonly discovery: WorkScanDiscovery;
  readonly onToggle: (room: string) => void;
}) {
  const atLimit = chosen.length >= WORK_SCAN_MAX_ROOMS;

  return (
    <div className="flex flex-col gap-2">
      <p className="font-mono text-xs text-muted" data-testid="workscan-discovery-counts">
        {`Okunan satir: ${String(discovery.lines_read)} · secilebilir: ${String(
          discovery.selectable.length,
        )} · okunamayan bicim: ${String(discovery.unusable_count)} · imlec (since): ${
          discovery.since === null ? "(yok)" : String(discovery.since)
        } · servisin last_seq degeri: ${String(discovery.last_seq)} · first_seq: ${
          discovery.first_seq === null ? "(bos)" : String(discovery.first_seq)
        } · belge ozeti: ${discovery.sha256.slice(0, 12)}`}
      </p>
      <StalenessLine staleness={discovery.staleness} testId="workscan-staleness-discovery" />
      <p className="text-xs text-muted">{discovery.room_name_caveat}</p>
      <p className="text-xs text-muted">{discovery.unlisted_note}</p>

      {/* The log is server-written and this build has no code path that could
          attempt a write to it. The sentence comes from the payload rather
          than from a constant here, so it is a claim the client reads back
          rather than one the screen makes on its own. */}
      <p className="text-xs text-muted" data-testid="workscan-discovery-write-refusal">
        {discovery.write_refusal}
      </p>

      {/* Separate from the staleness note above for the same reason it is
          separate on the scan result: a ring drop is a concrete loss, not a
          general caveat about freshness. */}
      {discovery.ring_drop !== null && (
        <Alert data-testid="workscan-discovery-ring-drop" status="warning">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Halka dususu: okumadiginiz satirlar dustu</Alert.Title>
            <Alert.Description>
              <span className="flex flex-col gap-1">
                <span>{discovery.ring_drop.detail}</span>
                <span className="font-mono text-xs">
                  {`since ${String(discovery.ring_drop.since)} · beklenen first_seq ${String(
                    discovery.ring_drop.expected_first,
                  )} · gelen first_seq ${String(discovery.ring_drop.first_seq)}`}
                </span>
              </span>
            </Alert.Description>
          </Alert.Content>
        </Alert>
      )}

      {discovery.entries.length === 0 ? (
        <p className="text-sm text-muted">
          Bu okumada gunlukte satir yok. Bu, yeni oda acilmadigi anlamina
          gelmez; yalnizca bu dilimde bir duyuru okunmadigi anlamina gelir.
        </p>
      ) : (
        <ul className="flex max-h-96 flex-col gap-2 overflow-y-auto">
          {discovery.entries.map((entry) => (
            <DiscoveryEntry
              atLimit={atLimit}
              busy={busy}
              entry={entry}
              isChosen={chosen.includes(entry.name)}
              key={`${String(entry.seq)}-${entry.name}`}
              onToggle={onToggle}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

/** What one scan produced, room by room, including what it could not read. */
function ScanReport({ scan }: { readonly scan: WorkScanResult }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="font-mono text-xs text-muted" data-testid="workscan-staleness-scan">
        {`Bu tarama ${formatDate(scan.started_at)} ile ${formatDate(
          scan.completed_at,
        )} arasinda, bir kez okundu. Okunan oda sayisi: ${String(scan.rooms.length)} · aday: ${String(
          scan.candidate_count,
        )} · reddedilen satir: ${String(scan.refusal_count)}.`}
      </p>
      <p className="text-xs text-muted">
        Bu yanit oda mesajlari icin sunucunun kendi bayatlik beyanini
        tasimiyor; yukaridaki degerler bu istasyonun olctugu okuma anlaridir.
        Sunucunun uc saniyelik beyani oda listesi icindir ve oda listesinin
        kendi anlik goruntusuyle birlikte gosterilir. Bir esik uydurulmadi.
      </p>

      {/* Separate from the staleness line above, and deliberately so: "the
          list may be a few seconds old" and "messages you never read are
          gone" are different findings, and folding the second into the first
          would turn a concrete loss into a general caveat (ADR-0007 5). */}
      <Alert data-testid="workscan-ring-drop" status="default">
        <Alert.Indicator />
        <Alert.Content>
          <Alert.Title>Halka dususu ayri bir sinyaldir</Alert.Title>
          <Alert.Description>
            <span className="flex flex-col gap-1">
              <span>
                Bu yanitta halka (ring) dususu sinyali yok. Tarama imlecsiz
                yapilir: &quot;since&quot; gonderilmez, ve sunucunun
                &quot;first_seq &gt; since + 1&quot; sinyali ancak imlecli bir
                okumada uretilir.
              </span>
              <span>
                Okunmamis mesajlarin halkadan dusmus olmasi bayatliktan ayri
                bir olaydir ve burada ayri gosterilir; birine bakip digerini
                varsaymayin.
              </span>
            </span>
          </Alert.Description>
        </Alert.Content>
      </Alert>

      {/* Not a failure: these rooms were read. It is the sentence the read
          path owes a person about *which* room they pointed at - an unlisted
          room is in no listing, so its name came from somewhere else, and an
          ephemeral one can expire on read, so an absent line proves nothing.
          No note is produced for an ordinary listed room, which makes this a
          distinction rather than a banner. */}
      {scan.notes.length > 0 && (
        <div className="flex flex-col gap-1" data-testid="workscan-room-notes">
          <p className="text-xs font-medium text-foreground">
            {`Okunan odalarin sinifi hakkinda (${String(scan.notes.length)})`}
          </p>
          {scan.notes.map((note) => (
            <p className="text-xs text-muted" key={`${note.room}-${note.kind}`}>
              {`• ${note.room} (${note.kind}): ${note.detail}`}
            </p>
          ))}
        </div>
      )}

      {scan.failures.length > 0 && (
        <Alert data-testid="workscan-failures" status="warning">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Okunamayan odalar</Alert.Title>
            <Alert.Description>
              <span className="flex flex-col gap-1">
                <span>
                  Asagidaki odalar okunamadi. Bu, o odalarda is olmadigi
                  anlamina gelmez; okunmadiklari anlamina gelir.
                </span>
                {scan.failures.map((failure) => (
                  <span className="font-mono text-xs" key={`${failure.room}-${failure.reason}`}>
                    {`${failure.room} · ${failure.reason} · ${failure.detail}`}
                  </span>
                ))}
              </span>
            </Alert.Description>
          </Alert.Content>
        </Alert>
      )}

      <ul className="flex flex-col gap-2">
        {scan.results.map((result) => (
          <li className="rounded-lg border border-border p-2" key={result.room}>
            <p className="font-mono text-xs text-muted">
              {`${result.room} · okunan satir: ${String(result.lines_read)} · aday: ${String(
                result.candidates.length,
              )} · reddedilen: ${String(result.refusals.length)}`}
            </p>
            {result.refusals.map((refusal) => (
              <p className="text-xs text-muted" key={`${refusal.room}-${String(refusal.seq)}`}>
                {`• Reddedildi (${refusal.shape}, sira ${String(refusal.seq)}): ${refusal.detail}`}
              </p>
            ))}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function WorkScanPanel() {
  const ids = useId();
  const [status, setStatus] = useState<WorkScanStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [step, setStep] = useState<Step>("read");

  // The scope, and the only addressable thing this surface sends. Plain React
  // state: never a browser store, and never seeded from one (SI-24).
  const [chosen, setChosen] = useState<readonly string[]>([]);
  const [candidateId, setCandidateId] = useState("");
  const [suggestion, setSuggestion] = useState<WorkScanSuggestion | null>(null);
  // Rooms a fresh reading stopped offering, kept so the scope can never
  // change under the user in silence.
  const [dropped, setDropped] = useState<readonly string[]>([]);

  /**
   * The one read that runs without a click.
   *
   * Safe precisely because it contacts nobody: it reports what a previous
   * user-initiated read found, or that none has run. It is not scheduled, not
   * repeated and not retried on its own.
   */
  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setBusy("read");
    try {
      setStatus(await fetchWorkScanStatus());
      setError(null);
    } catch (caught) {
      setError(toApiError(caught));
      setStep("read");
    } finally {
      setLoading(false);
      setBusy(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /**
   * Narrow the scope to what the newest reading actually offers, and say so.
   *
   * A room no reading offers must not stay in the scope: the next scan would
   * name a room this session was never shown. The offering is the **union** of
   * the two lists, and that matters now that there are two - filtering against
   * the overview alone would silently discard a room the user picked off the
   * discovery log, which is the same defect in the other direction.
   *
   * A room removed here is named rather than dropped quietly: the scope is the
   * one thing on this surface that reaches the wire, and changing it without
   * saying so would be this panel editing a user's request behind their back.
   */
  function narrowScope(next: WorkScanStatus): void {
    const offered = new Set([
      ...(next.room_index?.rooms ?? []).map((room) => room.name),
      ...(next.discovery?.selectable ?? []),
    ]);
    setChosen((current) => {
      setDropped(current.filter((room) => !offered.has(room)));
      return current.filter((room) => offered.has(room));
    });
  }

  async function readRooms(): Promise<void> {
    // Double-click guard. Two overviews in flight would spend two reads from
    // a per-IP bucket to learn the same thing.
    if (busy !== null) return;
    setBusy("rooms");
    setError(null);
    try {
      const next = await refreshWorkScanRooms();
      setStatus(next);
      narrowScope(next);
    } catch (caught) {
      setError(toApiError(caught));
      setStep("rooms");
    } finally {
      setBusy(null);
    }
  }

  /**
   * Read the discovery log once, because the user asked.
   *
   * `since` is passed in by the control that was pressed rather than held in
   * state: "read the newest lines" sends none, and "continue from where the
   * last read ended" sends the `last_seq` that read reported. Keeping a cursor
   * in state and reusing it would be the first half of a loop, and this
   * surface has no second half to give it.
   */
  async function readDiscovery(since: number | null): Promise<void> {
    if (busy !== null) return;
    setBusy("discovery");
    setError(null);
    try {
      const next = await refreshWorkScanDiscovery(since);
      setStatus(next);
      narrowScope(next);
    } catch (caught) {
      setError(toApiError(caught));
      setStep("discovery");
    } finally {
      setBusy(null);
    }
  }

  async function scan(): Promise<void> {
    if (busy !== null || chosen.length === 0) return;
    setBusy("scan");
    setError(null);
    setSuggestion(null);
    try {
      setStatus(await scanWorkRooms(chosen));
      // Candidate identities belong to one scan. Keeping the previous pick
      // would let a stale identifier be submitted against a new reading.
      setCandidateId("");
    } catch (caught) {
      setError(toApiError(caught));
      setStep("scan");
    } finally {
      setBusy(null);
    }
  }

  async function suggest(): Promise<void> {
    if (busy !== null || candidateId === "") return;
    setBusy("suggest");
    setError(null);
    try {
      setSuggestion(await suggestWorkScanCandidate(candidateId));
    } catch (caught) {
      setError(toApiError(caught));
      setStep("suggest");
    } finally {
      setBusy(null);
    }
  }

  function toggleRoom(room: string): void {
    setChosen((current) =>
      current.includes(room)
        ? current.filter((name) => name !== room)
        : current.length >= WORK_SCAN_MAX_ROOMS
          ? current
          : [...current, room],
    );
  }

  if (status === null) {
    return (
      <Card>
        <Card.Header>
          <Card.Title>Is tarama</Card.Title>
        </Card.Header>
        <Card.Content className="flex flex-col gap-3">
          {error === null ? (
            <p className="text-sm text-muted">Tarama yuzeyi okunuyor...</p>
          ) : (
            <ErrorRegion
              error={error}
              onRetry={() => void load()}
              retryPending={loading}
              section="Is Tara / Tarama yuzeyi"
              title={ERROR_TITLE[step]}
            />
          )}
        </Card.Content>
      </Card>
    );
  }

  const {
    capability,
    discovery,
    last_scan: lastScan,
    room_index: roomIndex,
  } = status;
  const candidates = (lastScan?.results ?? []).flatMap((result) => result.candidates);

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Card.Title>Is tarama</Card.Title>
          <StatusPill
            label={capability.ready ? "Modul ve yazma kapisi hazir" : "Modul veya yazma kapisi hazir degil"}
            tone={capability.ready ? "ok" : "pending"}
          />
        </div>
        <Card.Description>
          Sectiginiz acik odalar bir kez okunur ve okunanlardan aday is
          cikarilir. Hicbir sey gonderilmez, hicbir sey onaylanmaz ve hicbir
          oda siz secmeden taranmaz.
        </Card.Description>
      </Card.Header>

      <Card.Content className="flex flex-col gap-4">
        {error !== null && (
          <ErrorRegion
            error={error}
            onRetry={step === "read" ? () => void load() : undefined}
            retryPending={busy === "read"}
            section="Is Tara"
            title={ERROR_TITLE[step]}
          />
        )}

        {/* --- what a deterministic derivation cannot do ----------------- */}
        <section aria-label="Cikarim sinirlari" className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-foreground">Bu taramanin siniri</h3>
          <Alert status="warning">
            <Alert.Indicator />
            <Alert.Content>
              <Alert.Title>Anlamsal cikarim yoktur</Alert.Title>
              {/* The backend's sentence, verbatim, on every read - not only
                  beside a result (ADR-0007 2). */}
              <Alert.Description>
                <span data-testid="workscan-honesty">{status.honesty}</span>
              </Alert.Description>
              {/* The same honesty about the refusals. A pattern list that was
                  described as a structural block is a stronger promise than
                  the code keeps, so the sentence is here rather than in an
                  ADR the reader never opens. */}
              <Alert.Description>
                <span data-testid="workscan-prohibition">
                  {status.prohibition_statement}
                </span>
              </Alert.Description>
            </Alert.Content>
          </Alert>
          <p className="text-xs text-muted" data-testid="workscan-polling">
            {status.polling_statement}
          </p>
          <p className="font-mono text-xs text-muted">
            {`Hicbir istekte gonderilmeyen parametreler: ${status.never_sent_params.join(", ")}`}
          </p>
          <p className="text-xs text-muted">{capability.detail}</p>
        </section>

        <Separator />

        {/* --- the scope, chosen by the user ---------------------------- */}
        <section aria-label="Oda secimi" className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-foreground">Oda secimi</h3>
            <Button isDisabled={busy !== null} onPress={() => void readRooms()} variant="secondary">
              {busy === "rooms" ? "Oda listesi okunuyor..." : "Oda listesini oku"}
            </Button>
          </div>
          <p className="text-xs text-muted">
            Oda listesi yalnizca siz istediginizde okunur ve kendiliginden
            yenilenmez. Taramanin kapsami bu listeden veya asagidaki kesif
            gunlugunden sectiginiz odalardir; butun oda evreni taranmaz.
            Secilecek bir listenin olmasi, listeyi taramak icin bir yetki
            degildir: tavan iki yerde de ayni ve degismedi.
          </p>

          {roomIndex === null ? (
            <p className="text-sm text-muted">
              Oda listesi bu oturumda henuz okunmadi. Secim yapabilmek icin
              once listeyi okuyun.
            </p>
          ) : (
            <RoomChooser
              busy={busy !== null}
              chosen={chosen}
              index={roomIndex}
              onToggle={toggleRoom}
            />
          )}

          <div className="flex flex-wrap items-center gap-2">
            <Button isDisabled={busy !== null || chosen.length === 0} onPress={() => void scan()}>
              {busy === "scan" ? "Taraniyor..." : "Secili odalari tara"}
            </Button>
            <span className="text-xs text-muted" data-testid="workscan-scope">
              {chosen.length === 0
                ? "Once en az bir oda secin."
                : `Taranacak: ${chosen.join(", ")}`}
            </span>
          </div>

          {/* The scope changed under the user, so the panel says which rooms
              left it and why. A silent narrowing would be this screen editing
              a request the user made. */}
          {dropped.length > 0 && (
            <p className="text-xs text-muted" data-testid="workscan-scope-dropped">
              {`Son okumada su odalar artik sunulmuyor ve secimden cikarildi: ${dropped.join(
                ", ",
              )}. Bu, o odalarin yok oldugu anlamina gelmez; yalnizca bu okumada listede ve kesif gunlugunde bulunmadiklari anlamina gelir.`}
            </p>
          )}
        </section>

        <Separator />

        {/* --- the discovery log: what has opened lately ----------------- */}
        <section aria-label="Kesif gunlugu" className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-foreground">Kesif gunlugu</h3>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                isDisabled={busy !== null}
                onPress={() => void readDiscovery(null)}
                variant="secondary"
              >
                {busy === "discovery" ? "Kesif gunlugu okunuyor..." : "Kesif gunlugunu oku"}
              </Button>
              {discovery !== null && (
                // The cursor comes from the reading that produced it and goes
                // out on this press. It is not held between presses, so there
                // is nothing here a schedule could drive.
                <Button
                  isDisabled={busy !== null}
                  onPress={() => void readDiscovery(discovery.last_seq)}
                  variant="secondary"
                >
                  {`Bu okumanin devamini oku (since ${String(discovery.last_seq)})`}
                </Button>
              )}
            </div>
          </div>
          <p className="text-xs text-muted">
            Servisin kendi gunlugu, her yeni kamu odasi icin bir satir. Yalnizca
            siz istediginizde okunur, kendiliginden yenilenmez ve okunmasi bir
            tarama baslatmaz. Satirin bicimi yayimlanmis semada yok; Station bir
            ayristirici uydurmaz, okuyamadigi satiri geldigi gibi gosterir.
          </p>

          {discovery === null ? (
            <p className="text-sm text-muted">
              Kesif gunlugu bu oturumda henuz okunmadi. Bos bir gunluk ile
              okunmamis bir gunluk ayni sey degildir; hangisi oldugunu gormek
              icin okuyun.
            </p>
          ) : (
            <DiscoveryLog
              busy={busy !== null}
              chosen={chosen}
              discovery={discovery}
              onToggle={toggleRoom}
            />
          )}
        </section>

        <Separator />

        {/* --- what the scan read -------------------------------------- */}
        <section aria-label="Tarama sonucu" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">Tarama sonucu</h3>
          {lastScan === null ? (
            <p className="text-sm text-muted">
              Bu oturumda henuz tarama yapilmadi. Bu, taranacak is olmadigi
              anlamina gelmez.
            </p>
          ) : (
            <ScanReport scan={lastScan} />
          )}
        </section>

        <Separator />

        {/* --- candidates ---------------------------------------------- */}
        <section aria-label="Adaylar" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">Adaylar</h3>
          {candidates.length === 0 ? (
            <p className="text-sm text-muted">
              Gosterilecek aday yok. Bos bir aday listesi, okunan odalarda is
              olmadigini kanitlamaz: yukaridaki okunan satir sayilarina ve
              okunamayan odalara bakin.
            </p>
          ) : (
            <>
              <ul className="flex flex-col gap-3">
                {candidates.map((candidate) => (
                  <CandidateCard
                    candidate={candidate}
                    disabled={busy !== null}
                    groupName={`${ids}-candidate`}
                    key={candidate.id}
                    onChoose={setCandidateId}
                    selected={candidateId === candidate.id}
                  />
                ))}
              </ul>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  isDisabled={busy !== null || candidateId === ""}
                  onPress={() => void suggest()}
                >
                  {busy === "suggest" ? "Aciliyor..." : "Secili adayi yerel gorev olarak ac"}
                </Button>
                <span className="text-xs text-muted">
                  Bu islem yalnizca bu bilgisayarda bir kayit acar. Hicbir
                  mesaj gonderilmez ve gorev onaylanmaz.
                </span>
              </div>
            </>
          )}

          {suggestion !== null && (
            <Alert data-testid="workscan-suggestion" status="default">
              <Alert.Indicator />
              <Alert.Content>
                <Alert.Title>Aday yerel gorev olarak acildi</Alert.Title>
                <Alert.Description>
                  <span className="flex flex-col gap-1">
                    <span>{suggestion.detail}</span>
                    <span className="font-mono text-xs">
                      {`Gorev: ${suggestion.task_id.slice(0, 12)} · durum: ${suggestion.state} · modul: ${
                        suggestion.module_id
                      } · kaynak: ${suggestion.source_id}`}
                    </span>
                    {/* What of this request is actually readable, said in
                        both directions. A scanned request is stored as a
                        digest, so the text lives in the task's workspace as a
                        file; when that write did not happen the task is still
                        real and the sentence says what is missing rather than
                        leaving an empty directory to be discovered. */}
                    <span data-testid="workscan-suggestion-request-file">
                      {suggestion.request_file_detail}
                    </span>
                    <span>
                      Bu gorev onaylanmadi. Onaya gecirmek gorev yuzeyinde ayri
                      bir islemdir ve kullanicinin kendi eylemidir.
                    </span>
                  </span>
                </Alert.Description>
              </Alert.Content>
            </Alert>
          )}
        </section>

        <Separator />

        {/* --- external service records -------------------------------- */}
        <section aria-label="Dis servis kayitlari" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">Dis servis kayitlari</h3>
          <p className="text-xs text-muted">
            Asagidaki kayitlar birer inceleme notudur, bir entegrasyon degil.
            Station bu servislerin hicbirine istek gondermez ve hicbirinin
            verisini bir aday uretiminde kullanmaz.
          </p>
          {status.adapters.map((adapter) => (
            <AdapterRecord adapter={adapter} key={adapter.id} />
          ))}
        </section>
      </Card.Content>
    </Card>
  );
}
