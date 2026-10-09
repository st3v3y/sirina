import { createContext, useContext } from "react";
import type { Tag } from "./api";

// --- Shared shell state (tags + the recordings tag-filter, read by the dashboard) ---
export type ShellCtx = {
  tags: Tag[];
  reloadTags: () => Promise<void>;
  filterTag: number | null;
  setFilterTag: (id: number | null) => void;
};
export const ShellContext = createContext<ShellCtx | null>(null);
export function useShell(): ShellCtx {
  const v = useContext(ShellContext);
  if (!v) throw new Error("useShell must be used within <Shell>");
  return v;
}
