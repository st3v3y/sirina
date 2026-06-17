// A small promise-based confirm dialog. We can't use window.confirm() because
// Tauri's WKWebView returns false for it (so confirm-gated deletes silently no-op).
// This builds a lightweight modal in the DOM and works in any webview.
export function confirmDialog(message: string, confirmLabel = "Delete"): Promise<boolean> {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.style.cssText =
      "position:fixed;inset:0;background:rgba(0,0,0,.6);display:flex;align-items:center;" +
      "justify-content:center;z-index:9999;font:14px -apple-system,system-ui,sans-serif";
    const box = document.createElement("div");
    box.style.cssText =
      "background:#171717;border:1px solid #333;border-radius:10px;padding:20px;" +
      "max-width:360px;color:#e5e5e5;box-shadow:0 10px 40px rgba(0,0,0,.5)";
    const p = document.createElement("p");
    p.textContent = message;
    p.style.cssText = "margin:0 0 18px;line-height:1.4";
    const row = document.createElement("div");
    row.style.cssText = "display:flex;gap:8px;justify-content:flex-end";
    const cancel = document.createElement("button");
    cancel.textContent = "Cancel";
    cancel.style.cssText =
      "padding:6px 14px;border-radius:6px;background:#333;color:#e5e5e5;border:none;cursor:pointer";
    const ok = document.createElement("button");
    ok.textContent = confirmLabel;
    ok.style.cssText =
      "padding:6px 14px;border-radius:6px;background:#dc2626;color:#fff;border:none;cursor:pointer";

    const close = (value: boolean) => {
      window.removeEventListener("keydown", onKey);
      overlay.remove();
      resolve(value);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close(false);
      if (e.key === "Enter") close(true);
    };
    cancel.onclick = () => close(false);
    ok.onclick = () => close(true);
    overlay.onclick = (e) => {
      if (e.target === overlay) close(false);
    };
    window.addEventListener("keydown", onKey);

    row.append(cancel, ok);
    box.append(p, row);
    overlay.append(box);
    document.body.append(overlay);
    ok.focus();
  });
}
