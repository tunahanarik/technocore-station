import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { cwd } from "node:process";

import { describe, expect, it } from "vitest";

/**
 * The HeroUI surface this app is allowed to use.
 *
 * Every component here has been checked against the v3 documentation and
 * rendered under the strict CSP. Reaching for a new one is not a styling
 * decision: an unverified component can pull an inline style (A1-R1), a v2
 * pattern or a paid component into the bundle. Widening the set is a
 * deliberate act, so it has to be done here, in the open, and never as a
 * side effect of an import line.
 *
 * `Tabs` was removed by ADR-0001 item 2, which replaced the three-tab layout
 * with the left-nav dashboard. It stays out.
 */
const ALLOWED_COMPONENTS = [
  "Alert",
  "Button",
  "Card",
  "Checkbox",
  "Chip",
  "Input",
  "Label",
  "Modal",
  "Separator",
  "TextField",
] as const;

/**
 * The `src` tree, found from the working directory.
 *
 * `import.meta.url` is an http URL under the jsdom environment, so it cannot
 * be turned into a path here. Both plausible working directories are checked
 * and anything else fails loudly rather than scanning an empty tree.
 */
function resolveSrcDir(): string {
  const candidates = [join(cwd(), "src"), join(cwd(), "apps", "station-web", "src")];
  const found = candidates.find((candidate) => existsSync(join(candidate, "App.tsx")));
  if (found === undefined) {
    throw new Error(`station-web/src not found from ${cwd()}`);
  }
  return found;
}

const SRC_DIR = resolveSrcDir();

const IMPORT_RE = /import\s*(?:type\s+)?\{([^}]*)\}\s*from\s*"@heroui\/react"/g;

function sourceFiles(directory: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const full = join(directory, entry.name);
    if (entry.isDirectory()) {
      found.push(...sourceFiles(full));
    } else if (/\.tsx?$/.test(entry.name)) {
      found.push(full);
    }
  }
  return found;
}

/** Every identifier this app imports from `@heroui/react`, across `src`. */
function importedComponents(): Map<string, string[]> {
  const byComponent = new Map<string, string[]>();
  for (const file of sourceFiles(SRC_DIR)) {
    const contents = readFileSync(file, "utf8");
    for (const match of contents.matchAll(IMPORT_RE)) {
      for (const raw of (match[1] ?? "").split(",")) {
        // "type Foo" and "Foo as Bar" both name Foo as the import.
        const name = raw.trim().replace(/^type\s+/, "").split(/\s+as\s+/)[0]?.trim() ?? "";
        if (name === "") continue;
        byComponent.set(name, [...(byComponent.get(name) ?? []), file]);
      }
    }
  }
  return byComponent;
}

describe("HeroUI component surface", () => {
  it("imports exactly the reviewed component set and nothing new", () => {
    const used = [...importedComponents().keys()].sort();
    expect(used).toEqual([...ALLOWED_COMPONENTS]);
  });

  it("no longer imports the retired Tabs component", () => {
    expect(importedComponents().has("Tabs")).toBe(false);
  });

  it("finds the source tree it is meant to be guarding", () => {
    // A guard that silently scans nothing passes forever.
    expect(sourceFiles(SRC_DIR).length).toBeGreaterThan(10);
  });
});
