const FEED_SERVER = "http://localhost:5555/ingest";
const BATCH_INTERVAL_MS = 3000; // flush to server every 3 seconds

let enabled = false;
let pendingDomains = new Set();

// --- Persist enabled state across browser restarts ---
browser.storage.local.get("enabled").then((result) => {
  enabled = result.enabled ?? false;
});

// --- Receive domains from content scripts ---
browser.runtime.onMessage.addListener((msg) => {
  if (msg.type !== "DOMAINS" || !enabled) return;
  msg.domains.forEach((d) => pendingDomains.add(d));
});

// --- Toggle on/off from popup ---
browser.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "GET_STATE") {
    sendResponse({ enabled });
    return true;
  }
  if (msg.type === "SET_STATE") {
    enabled = msg.enabled;
    browser.storage.local.set({ enabled });
    sendResponse({ enabled });
    return true;
  }
});

// --- Batch flush to feed server ---
setInterval(async () => {
  if (!enabled || pendingDomains.size === 0) return;

  const batch = [...pendingDomains];
  pendingDomains.clear();

  try {
    await fetch(FEED_SERVER, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains: batch }),
    });
  } catch (_) {
    // Server not running — silently drop. No retry to avoid memory growth.
  }
}, BATCH_INTERVAL_MS);
