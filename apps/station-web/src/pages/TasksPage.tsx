import { TasksPanel } from "../components/tasks/TasksPanel";

/**
 * Gorevler: the task surface and the agent's deterministic tool runner.
 *
 * A thin mount, like `WorkScanPage` around its panel. The whole section is
 * one panel on purpose: the honesty block that qualifies every run - closed
 * execution, an unimplemented test result, a ceiling in three units - has to
 * be on the same screen as the button that starts one. Splitting them would
 * let a reader approve a plan without the sentences that say what approving
 * it does and does not mean.
 */
export function TasksPage() {
  return <TasksPanel />;
}
