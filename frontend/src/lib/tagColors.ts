// Token names are persisted in the DB; their *styles* map to the warm palette
// (see --color-cat-* in index.css), so existing tag colors render without a migration.
export const TAG_COLORS = ["sky", "emerald", "violet", "amber", "rose", "teal", "neutral"] as const;

const CATS = new Set<string>(TAG_COLORS);

/** CSS color for a stored tag/speaker color token. */
export function catColor(color: string | null): string {
  const c = color && CATS.has(color) ? color : "neutral";
  return `var(--color-cat-${c})`;
}
