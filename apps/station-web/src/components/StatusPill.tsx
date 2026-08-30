import { Chip } from "@heroui/react";

/**
 * A status indicator that never relies on colour alone.
 *
 * Every pill carries a glyph and a text label in addition to its colour, and
 * a screen-reader-only sentence naming the state, so the meaning survives
 * greyscale, colour blindness and assistive technology.
 */

export type StatusTone = "ok" | "pending" | "inactive" | "problem";

interface ToneStyle {
  readonly color: "success" | "warning" | "default" | "danger";
  readonly glyph: string;
  readonly spokenState: string;
}

const TONES: Record<StatusTone, ToneStyle> = {
  ok: { color: "success", glyph: "✓", spokenState: "iyi" },
  pending: { color: "warning", glyph: "…", spokenState: "bekliyor" },
  inactive: { color: "default", glyph: "—", spokenState: "etkin degil" },
  problem: { color: "danger", glyph: "!", spokenState: "sorunlu" },
};

interface StatusPillProps {
  readonly tone: StatusTone;
  readonly label: string;
}

export function StatusPill({ tone, label }: StatusPillProps) {
  const style = TONES[tone];
  return (
    <Chip color={style.color} size="sm" variant="soft">
      <span aria-hidden="true">{style.glyph}</span>
      <Chip.Label>{label}</Chip.Label>
      <span className="sr-only">{` (durum: ${style.spokenState})`}</span>
    </Chip>
  );
}
