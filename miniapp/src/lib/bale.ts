// A thin, typed doorway to Bale's Mini App SDK (window.Bale.WebApp, https://docs.bale.ai/miniapp).
// Outside Bale (the local preview) the object is missing and every call quietly does nothing.

type InvoiceStatus = "paid" | "cancelled" | "failed" | "pending";

interface BaleWebApp {
  initData: string;
  version?: string;
  ready(): void;
  expand(): void;
  close(): void;
  setHeaderColor?(color: string): void;
  openLink?(url: string): void;
  openInvoice?(params: unknown, callback: (result: { status: InvoiceStatus }) => void): void;
  BackButton?: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
  HapticFeedback?: { impactOccurred(style: string): void; notificationOccurred(type: string): void };
}

export const webApp: BaleWebApp | undefined = (window as unknown as { Bale?: { WebApp?: BaleWebApp } }).Bale?.WebApp;
export const initData = webApp?.initData ?? "";
export const insideBale = initData.length > 0;

export function startBale(): void {
  try {
    webApp?.ready();
    webApp?.expand();
    webApp?.setHeaderColor?.("#120d1c");
  } catch {
    /* an old client: the page still works */
  }
}

export function haptic(kind: "tap" | "success" | "error" = "tap"): void {
  if (!insideBale) return;
  try {
    if (kind === "tap") webApp?.HapticFeedback?.impactOccurred("light");
    else webApp?.HapticFeedback?.notificationOccurred(kind);
  } catch {
    /* no haptics on this client */
  }
}

/** Open Bale's own payment sheet for an invoice the server created; resolves with how it ended. */
export function openInvoice(params: unknown): Promise<InvoiceStatus | "unsupported"> {
  return new Promise((resolve) => {
    if (!insideBale || !webApp?.openInvoice) return resolve("unsupported");
    try {
      webApp.openInvoice(params, (result) => resolve(result?.status ?? "failed"));
    } catch {
      resolve("unsupported");
    }
  });
}

/** Show Bale's back button while ``handler`` is set; returns the function that takes it away again. */
export function onBack(handler: (() => void) | null): () => void {
  const button = insideBale ? webApp?.BackButton : undefined;  // outside Bale the SDK is loaded but has nobody to talk to
  if (!button) return () => {};
  try {
    if (!handler) {
      button.hide();
      return () => {};
    }
    button.show();
    button.onClick(handler);
    return () => {
      try {
        button.offClick(handler);
      } catch {
        /* the client went away */
      }
    };
  } catch {
    return () => {};
  }
}

export function openLink(url: string): void {
  try {
    if (insideBale && webApp?.openLink) return webApp.openLink(url);
  } catch {
    /* fall through to the browser */
  }
  window.open(url, "_blank", "noopener");
}
