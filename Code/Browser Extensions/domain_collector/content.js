// Runs on every page. Collects the current page's domain
// plus any unique domains found in <a href> links.
// Sends them to the background script, which decides whether to forward them.

(function () {
  const domains = new Set();

  // Current page domain
  try {
    domains.add(new URL(window.location.href).hostname);
  } catch (_) {}

  // All link domains
  document.querySelectorAll("a[href]").forEach((a) => {
    try {
      const host = new URL(a.href).hostname;
      if (host) domains.add(host);
    } catch (_) {}
  });

  if (domains.size > 0) {
    browser.runtime.sendMessage({
      type: "DOMAINS",
      domains: [...domains],
    });
  }
})();
