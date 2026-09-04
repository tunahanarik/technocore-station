/**
 * Risk A1-R1, finally measured.
 *
 * `PROJECT_STATUS.md` has carried this since package A: the strict CSP forbids
 * inline `<style>` **elements**, React Aria injects exactly one at runtime, and
 * the policy permits it by a single SHA-256 hash
 * (`REACT_ARIA_PRESSABLE_STYLE_HASH`). Any HeroUI or React Aria upgrade can
 * invalidate that hash, and the failure is silent in every test the repository
 * had: jsdom does not implement CSP, so no Vitest test could see the style get
 * blocked. Only a real browser loading the real production bundle behind the
 * real security headers can.
 *
 * The test is written so that it cannot pass vacuously. "No violation logged"
 * is worthless if the policy is missing, and equally worthless if the style
 * element never existed. So all three are asserted: the header is present and
 * strict, the injected stylesheet is present **and applied**, and the console
 * is clean.
 */

import { SECTION_LABELS, expect, gotoSection, openApp, test } from "../fixtures";

test.describe("Content Security Policy", () => {
  test("the document is served with the strict policy", async ({ page }) => {
    await openApp(page);
    // Reload rather than a cold `goto`: the session cookie is already set, so
    // this is the document a user actually reads, not an unauthenticated one.
    const response = await page.reload({ waitUntil: "domcontentloaded" });
    const csp = response?.headers()["content-security-policy"];

    expect(csp, "the SPA document must carry a CSP header").toBeTruthy();
    expect(csp).toContain("default-src 'none'");
    expect(csp).toContain("script-src 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("base-uri 'none'");
    expect(csp).toContain("form-action 'none'");
    // The hash that makes A1-R1 a risk in the first place.
    expect(csp).toMatch(/style-src 'self' 'sha256-[A-Za-z0-9+/=]+'/);
    expect(csp, "script-src must never be loosened").not.toContain("script-src 'self' 'unsafe");
  });

  test("the React Aria stylesheet is admitted by its hash and actually applies", async ({
    page,
  }) => {
    await openApp(page);

    // Mount every ready section: each one brings more React Aria widgets, and
    // the injection happens on first mount of a pressable component.
    for (const label of SECTION_LABELS) {
      await gotoSection(page, label);
    }

    const verdict = await page.evaluate(() => {
      const styles = [...document.querySelectorAll("style")];
      const pressable = styles.filter((element) =>
        element.textContent?.includes("data-react-aria-pressable"),
      );
      return {
        total: styles.length,
        pressableCount: pressable.length,
        // A CSP-blocked inline <style> element is parsed into the DOM but is
        // never applied: its `sheet` stays null. This is the difference
        // between "the hash matched" and "nothing broke because nothing ran".
        applied: pressable.map((element) => (element.sheet?.cssRules.length ?? 0) > 0),
        text: pressable.map((element) => element.textContent ?? ""),
      };
    });

    expect(
      verdict.pressableCount,
      "React Aria no longer injects the pressable stylesheet: the pinned hash may now be dead code",
    ).toBeGreaterThan(0);
    expect(
      verdict.applied,
      "the pressable stylesheet was inserted but not applied - the pinned CSP hash no longer matches it",
    ).not.toContain(false);
    expect(verdict.text.join("\n")).toContain("touch-action");
  });

  test("no CSP violation is reported on any section", async ({ page, consoleLog }) => {
    await openApp(page);

    for (const label of SECTION_LABELS) {
      await gotoSection(page, label);
      await expect(page.getByRole("main")).toBeVisible();
    }

    expect(consoleLog.cspViolations(), "CSP refusals reported by the browser").toEqual([]);
    expect(consoleLog.pageErrors).toEqual([]);
  });

  test("the policy stops the page from reaching the network at all", async ({
    page,
    consoleLog,
    outbound,
  }) => {
    await openApp(page);

    // `connect-src` inherits `default-src 'none'`, so the browser refuses the
    // connection before a request is created. This is a stronger guarantee
    // than the test harness's own blocker, and it ships in the product.
    consoleLog.allow(/Content Security Policy|Refused to connect/i);

    const reached = await page.evaluate(async () => {
      try {
        await fetch("https://technocore.chat/healthz", { mode: "no-cors" });
        return true;
      } catch {
        return false;
      }
    });

    expect(reached).toBe(false);
    expect(consoleLog.cspViolations().join("\n")).toMatch(/technocore\.chat/);
    // No request was ever issued, so the harness meter has nothing to report.
    expect(outbound.external()).toEqual([]);
  });

  test("security headers accompany the document", async ({ page }) => {
    await openApp(page);
    const response = await page.reload({ waitUntil: "domcontentloaded" });
    const headers = response?.headers() ?? {};

    expect(headers["referrer-policy"]).toBe("no-referrer");
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["x-frame-options"]).toBe("DENY");
    expect(headers["cross-origin-opener-policy"]).toBe("same-origin");
    expect(headers["cross-origin-resource-policy"]).toBe("same-origin");
    expect(headers["permissions-policy"]).toBeTruthy();
    // INV/SI: no CORS anywhere, on any response.
    expect(headers["access-control-allow-origin"]).toBeUndefined();
  });
});
