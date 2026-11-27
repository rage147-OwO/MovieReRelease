"use strict";

(() => {
  const api = globalThis.WEEKLY_EMAIL_API;
  if (!api) return;

  const form = document.getElementById("weekly-email-form");
  const fields = document.getElementById("weekly-email-fields");
  const email = document.getElementById("weekly-email-address");
  const status = document.getElementById("weekly-email-status");
  const confirmForm = document.getElementById("weekly-email-confirm");
  const confirmNote = document.getElementById("weekly-email-confirm-note");
  const confirmButton = document.getElementById("weekly-email-confirm-button");
  let confirmation;

  async function post(path, body) {
    const response = await fetch(api.replace(/\/$/, "") + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "omit",
    });
    if (response.status === 410) return "expired";
    if (response.status === 429) return "limited";
    if (response.status === 400 && path === "/request") return "invalid";
    if (!response.ok) throw new Error("Email request failed");
    return "ok";
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const action = event.submitter?.value || "subscribe";
    fields.disabled = true;
    status.textContent = "요청을 보내고 있어요.";
    try {
      const result = await post("/request", { action, email: email.value });
      const message = {
        limited: "요청이 많아요. 잠시 후 다시 시도해 주세요.",
        invalid: "이메일 주소를 확인해 주세요.",
        ok: "요청을 받았어요. 해당 주소에서 확인 메일을 확인해 주세요.",
      };
      status.textContent = message[result];
      if (result === "ok") form.reset();
    } catch {
      status.textContent = "요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.";
    } finally {
      fields.disabled = false;
    }
  });

  function showConfirmation() {
    confirmation = /^#weekly-email=(subscribe|unsubscribe)\.([a-f0-9]{64})$/.exec(location.hash);
    confirmForm.hidden = !confirmation;
    form.hidden = Boolean(confirmation);
    if (!confirmation) return;
    const enrolling = confirmation[1] === "subscribe";
    confirmNote.textContent = enrolling
      ? "이메일 주소를 등록하고 주간 소식을 받을까요?"
      : "이메일 주소를 삭제하고 주간 소식 받기를 중단할까요?";
    confirmButton.textContent = enrolling ? "등록 확인" : "삭제 확인";
    document.getElementById("notify-info-btn").click();
    confirmButton.focus();
  }

  confirmForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const [, action, token] = confirmation;
    confirmButton.disabled = true;
    try {
      const result = await post("/confirm", { action, token });
      if (result === "limited") {
        confirmNote.textContent = "요청이 많아요. 잠시 후 다시 시도해 주세요.";
        return;
      }
      history.replaceState(null, "", location.pathname + location.search);
      showConfirmation();
      status.textContent = result === "expired"
        ? "확인 링크가 만료되었거나 이미 사용됐어요. 다시 요청해 주세요."
        : action === "subscribe" ? "주간 이메일을 등록했어요." : "등록된 이메일 주소를 삭제했어요.";
      email.focus();
    } catch {
      confirmNote.textContent = "확인하지 못했어요. 잠시 후 다시 시도해 주세요.";
    } finally {
      confirmButton.disabled = false;
    }
  });

  async function checkSender() {
    try {
      const response = await fetch(api.replace(/\/$/, "") + "/status", {
        credentials: "omit",
        cache: "no-store",
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) return;
      fields.disabled = false;
      status.textContent = "등록과 삭제는 이메일로 확인해요.";
    } catch {
      // Keep the form disabled until the mail service can be reached.
    }
  }

  window.addEventListener("hashchange", showConfirmation);
  showConfirmation();
  checkSender();
})();
