/**
 * Rendering a hash without rendering something that looks like a seed.
 *
 * A SHA-256 digest is 64 hex characters. So is a 32-byte secret seed. The app
 * has a standing rule that no 64-hex run may ever reach the DOM (tested on
 * several surfaces), which is only enforceable if there is one obvious way to
 * put a digest on screen - hence this function rather than a `slice(0, 12)`
 * repeated at every call site, where the twelfth one is eventually a `slice`
 * of the whole string.
 *
 * Twelve characters is enough for a human to compare two values by eye and far
 * too few to reconstruct the original.
 */
export const DIGEST_PREFIX_CHARS = 12;

export function shortDigest(value: string): string {
  return value.slice(0, DIGEST_PREFIX_CHARS);
}
