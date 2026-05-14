const toggle = document.getElementById("toggle");
const status = document.getElementById("status");

function applyState(enabled) {
  toggle.checked = enabled;
  status.textContent = enabled ? "collecting domains…" : "off";
  status.className = "status" + (enabled ? " on" : "");
}

// Load current state
browser.runtime.sendMessage({ type: "GET_STATE" }).then((res) => {
  applyState(res.enabled);
});

// Handle toggle
toggle.addEventListener("change", () => {
  browser.runtime
    .sendMessage({ type: "SET_STATE", enabled: toggle.checked })
    .then((res) => applyState(res.enabled));
});
