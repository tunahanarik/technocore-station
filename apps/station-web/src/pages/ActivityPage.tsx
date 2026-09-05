import { ActivityPanel } from "../components/activity/ActivityPanel";

/**
 * Aktivite: the Activity Desk.
 *
 * Opened in the same package as Gorevler and never before it (ADR-0008 8):
 * a timeline whose rows carry run and task identifiers, shown while the
 * section that owns those identifiers is still hidden, would be a list of
 * events with no way to reach what they happened to.
 */
export function ActivityPage() {
  return <ActivityPanel />;
}
