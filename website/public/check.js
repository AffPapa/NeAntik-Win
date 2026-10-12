"use strict";

const show = (id, value) => {
  const element = document.getElementById(id);
  if (element) element.textContent = value == null || value === "" ? "Недоступно" : String(value);
};

show("ua", navigator.userAgent);
show("languages", (navigator.languages || []).join(", "));
show("timezone", Intl.DateTimeFormat().resolvedOptions().timeZone);
show("screen", `${screen.width} × ${screen.height} · ${window.devicePixelRatio}× · ${screen.colorDepth} bit`);
show("hardware", `${navigator.hardwareConcurrency ?? "?"} потоков · ${navigator.deviceMemory ?? "?"} ГБ`);

try {
  const canvas = document.createElement("canvas");
  const gl = canvas.getContext("webgl");
  const debug = gl && gl.getExtension("WEBGL_debug_renderer_info");
  show("webgl", debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : gl ? "Доступен; подробный renderer скрыт" : "Недоступен");
} catch {
  show("webgl", "Недоступен");
}

async function permissionState(name, id) {
  if (!navigator.permissions?.query) { show(id, "API недоступен"); return; }
  try {
    const result = await navigator.permissions.query({ name });
    const labels = { granted: "Разрешено", denied: "Заблокировано", prompt: "Запрос разрешения" };
    show(id, labels[result.state] || result.state);
  } catch {
    show(id, "Браузер не сообщает");
  }
}

permissionState("geolocation", "geo");
permissionState("notifications", "notifications");
permissionState("camera", "camera");
permissionState("microphone", "microphone");

document.getElementById("check-ip")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  show("ip", "Проверка…");
  try {
    const response = await fetch("/api/ip", { cache: "no-store", credentials: "omit" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    show("ip", result.ip || "Хостинг не сообщил адрес");
    show("country", result.country || "Недоступно");
  } catch {
    show("ip", "Запрос не удался");
    show("country", "Не проверено");
  } finally {
    button.disabled = false;
  }
});

document.getElementById("check-headers")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  show("ua-match", "Проверка…");
  try {
    const response = await fetch("/api/headers", { cache: "no-store", credentials: "omit" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    show("http-ua", result.userAgent);
    show("http-language", result.acceptLanguage);
    show("ua-match", result.userAgent === navigator.userAgent ? "Совпадает в этой проверке" : "Не совпадает — проверьте настройки браузера");
  } catch {
    show("ua-match", "Запрос не удался");
  } finally {
    button.disabled = false;
  }
});
