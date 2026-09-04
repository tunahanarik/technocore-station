/**
 * Start one real backend for the whole browser-test run, and take it down
 * again afterwards.
 *
 * One process, one throwaway data directory, one ephemeral loopback port. The
 * run directory's path is exported through the environment so every worker
 * can find the origin and mint its own single-use session token; the
 * directory itself, database included, is deleted in the teardown.
 */

import { RUN_DIR_ENV, startStation } from "./harness/station";

export default async function globalSetup(): Promise<() => Promise<void>> {
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
