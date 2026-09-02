// STAGED NEGATIVE PROOF for the CI frontend job (Paket A).
// This file exists for exactly one commit, to demonstrate that the new
// workflow's frontend job can actually fail. It is reverted immediately in
// the next commit; both commits stay in history on purpose.
import { expect, it } from "vitest";

it("ci negative proof: this failure is deliberate and will be reverted", () => {
  expect("the frontend job can fail").toBe("proven when this run is red");
});
