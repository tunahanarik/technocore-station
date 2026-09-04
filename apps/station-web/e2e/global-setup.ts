/**
 * Start one real backend for the whole browser-test run, and take it down
 * again afterwards.
 *
 * One process, one throwaway data directory, one ephemeral loopback port. The
 * run directory's path is exported through the environment so every worker
 * can find the origin and mint its own single-use session token; the
 * directory itself, database included, is deleted in the teardown.
 *
 * The suite's rules about itself are checked here, first, before anything is
 * started. Global setup runs before Playwright has selected a single test, so
 * a committed `only`, a committed `skip` or a filtered command line cannot
 * prevent it - which is precisely how the previous arrangement failed: the
 * rules lived only in a spec, and `only` mode filtered that spec out along
 * with everything else.
 */

import { assertSuiteDiscipline } from "./harness/discipline";
import { RUN_DIR_ENV, startStation } from "./harness/station";

export default async function globalSetup(): Promise<() => Promise<void>> {
  await assertSuiteDiscipline();

  const station = await startStation();

  // Workers are forked after this returns, so they inherit both values.
  process.env.STATION_E2E_ORIGIN = station.handshake.origin;
  process.env.STATION_E2E_DATA_DIR = station.handshake.data_dir;

  if (process.env[RUN_DIR_ENV] === undefined) {
    throw new Error("startStation did not publish the run directory");
  }

  return async () => {
    await station.stop();
  };
}
