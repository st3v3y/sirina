import { addCollection, getIcon, Icon as Iconify } from "@iconify/react";
// A committed subset of lucide (only the icons we use), so it's offline — no requests to
// the Iconify API at runtime — and lean. Regenerate the JSON if a new glyph is needed.
import lucide from "../lib/lucide-icons.json";

addCollection(lucide as Parameters<typeof addCollection>[0]);

export type IconName = string; // a lucide icon name, e.g. "mic", "settings", "chevron-down"

export function Icon({
  name,
  size = 16,
  className,
}: {
  name: IconName;
  size?: number | string;
  className?: string;
}) {
  const icon = `lucide:${name}`;
  // Guard: an unregistered icon would otherwise trigger an Iconify API fetch. Since we
  // bundle icons offline, render an empty placeholder instead — never a network call.
  if (!getIcon(icon)) {
    return <span className={className} style={{ display: "inline-block", width: size, height: size }} />;
  }
  return <Iconify icon={icon} width={size} height={size} className={className} />;
}
