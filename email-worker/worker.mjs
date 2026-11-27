import { buildDigest } from "./digest.mjs";

const CONFIRMATION_TTL = 24 * 60 * 60 * 1000;
const REQUEST_INTERVAL = 15 * 60 * 1000;
const EMAIL = /^[a-z0-9.!#$%&'*+\/=?^_~-]+@(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i;
const TOKEN = /^[a-f0-9]{64}$/;

function toHex(bytes) {
  return Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
}

function newToken() {
  return toHex(crypto.getRandomValues(new Uint8Array(32)));
}

function emailLink(site, action, token) {
  const url = new URL(site);
  url.hash = "weekly-email=" + action + "." + token;
  return url.href;
}

function mailConfigured(env) {
  return Boolean(env.BREVO_API_KEY && env.MAIL_FROM);
}

async function mailRequestId(key) {
  const bytes = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(key)));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = toHex(bytes.subarray(0, 16));
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join("-");
}

async function sendEmail(env, email, subject, text, idempotencyKey) {
  if (!mailConfigured(env)) throw new Error("Mail sender is not configured");
  const response = await fetch("https://api.brevo.com/v3/smtp/email", {
    method: "POST",
    headers: {
      "api-key": env.BREVO_API_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      sender: { email: env.MAIL_FROM, name: "재개봉 알리미" },
      to: [{ email }],
      subject,
      textContent: text,
      headers: { idempotencyKey: await mailRequestId(idempotencyKey) },
    }),
    signal: AbortSignal.timeout(10000),
  });
  if (response.ok) return;
  if (response.status === 400 || response.status === 409) {
    const detail = await response.json().catch(() => null);
    if (detail?.code === "duplicate_parameter" && /idempotency/i.test(detail.message || "")) return;
  }
  throw new Error("Mail provider returned " + response.status);
}

async function requestChange(env, action, email, now) {
  if (!mailConfigured(env)) throw new Error("Mail sender is not configured");
  if (action === "subscribe") {
    const token = newToken();
    const pending = await env.DB.prepare(
      "INSERT INTO pending_subscriptions(email, token, requested_at) " +
      "SELECT ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM subscribers WHERE email = ?) " +
      "ON CONFLICT(email) DO UPDATE SET token = excluded.token, requested_at = excluded.requested_at " +
      "WHERE pending_subscriptions.requested_at <= ? RETURNING token",
    ).bind(email, token, now, email, now - REQUEST_INTERVAL).first();
    if (!pending) return;
    const link = emailLink(env.SITE_URL, action, token);
    await sendEmail(env, email, "재개봉 알리미 이메일 등록 확인",
      "아래 링크를 열고 등록을 확인해 주세요. 링크는 24시간 동안 유효해요.\n\n" + link,
      "registration/" + token);
    return;
  }

  const subscription = await env.DB.prepare(
    "UPDATE subscribers SET last_remove_request = ? WHERE email = ? AND last_remove_request <= ? " +
    "RETURNING unsubscribe_token",
  ).bind(now, email, now - REQUEST_INTERVAL).first();
  if (!subscription) return;
  const link = emailLink(env.SITE_URL, action, subscription.unsubscribe_token);
  await sendEmail(env, email, "재개봉 알리미 이메일 삭제 확인",
    "아래 링크를 열고 이메일 주소 삭제를 확인해 주세요.\n\n" + link,
    "removal/" + subscription.unsubscribe_token + "/" + now);
}

async function confirmChange(env, action, token, now) {
  if (action === "unsubscribe") {
    const removed = await env.DB.prepare(
      "DELETE FROM subscribers WHERE unsubscribe_token = ? RETURNING email",
    ).bind(token).first();
    return Boolean(removed);
  }

  const [insert] = await env.DB.batch([
    env.DB.prepare(
      "INSERT INTO subscribers(email, unsubscribe_token) " +
      "SELECT email, ? FROM pending_subscriptions WHERE token = ? AND requested_at >= ? " +
      "ON CONFLICT(email) DO NOTHING RETURNING email",
    ).bind(newToken(), token, now - CONFIRMATION_TTL),
    env.DB.prepare("DELETE FROM pending_subscriptions WHERE token = ?").bind(token),
  ]);
  return insert.results.length > 0;
}

async function handleRequest(request, env) {
  const origin = new URL(env.SITE_URL).origin;
  if (request.headers.get("Origin") !== origin) return new Response(null, { status: 403 });
  const headers = {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Cache-Control": "no-store",
    "Vary": "Origin",
  };
  const respond = status => new Response(null, { status, headers });
  const { pathname } = new URL(request.url);
  if (pathname === "/status") {
    return respond(request.method !== "GET" ? 405 : mailConfigured(env) ? 204 : 503);
  }
  if (pathname !== "/request" && pathname !== "/confirm") return respond(404);
  if (request.method === "OPTIONS") return respond(204);
  if (request.method !== "POST") return respond(405);
  if (!/^application\/json(?:;|$)/i.test(request.headers.get("Content-Type") || "")) return respond(415);
  if (Number(request.headers.get("Content-Length")) > 1024) return respond(413);

  try {
    const key = pathname + ":" + (request.headers.get("CF-Connecting-IP") || "local");
    if (!(await env.EMAIL_REQUEST_LIMIT.limit({ key })).success) return respond(429);
    const text = await request.text();
    if (text.length > 1024) return respond(413);
    const data = JSON.parse(text);
    if (data?.action !== "subscribe" && data?.action !== "unsubscribe") return respond(400);
    if (pathname === "/confirm") {
      if (typeof data.token !== "string" || !TOKEN.test(data.token)) return respond(400);
      return respond(await confirmChange(env, data.action, data.token, Date.now()) ? 204 : 410);
    }
    const email = typeof data.email === "string" ? data.email.trim().toLowerCase() : "";
    if (email.length > 254 || !EMAIL.test(email)) return respond(400);
    await requestChange(env, data.action, email, Date.now());
    return respond(204);
  } catch (error) {
    if (error instanceof SyntaxError) return respond(400);
    return respond(503);
  }
}

async function loadData(site, file) {
  const result = await fetch(new URL("data/" + file, site), {
    cache: "no-store",
    signal: AbortSignal.timeout(10000),
  });
  if (!result.ok) throw new Error("Cannot load " + file + ": " + result.status);
  return result.json();
}

async function sendWeeklyDigest(time, env) {
  await env.DB.prepare("DELETE FROM pending_subscriptions WHERE requested_at < ?")
    .bind(time - CONFIRMATION_TTL).run();
  if (!await env.DB.prepare("SELECT 1 FROM subscribers LIMIT 1").first()) return;

  const [movies, theaters] = await Promise.all([
    loadData(env.SITE_URL, "movies.json"),
    loadData(env.SITE_URL, "theaters.json"),
  ]);
  const digest = buildDigest(time, env.SITE_URL, movies, theaters);
  let cursor = "";
  let failures = 0;
  for (;;) {
    const { results: batch } = await env.DB.prepare(
      "SELECT email, unsubscribe_token FROM subscribers " +
      "WHERE email > ? AND last_digest_week < ? ORDER BY email LIMIT 50",
    ).bind(cursor, digest.week).all();
    if (batch.length === 0) break;
    for (const { email, unsubscribe_token: token } of batch) {
      try {
        const link = emailLink(env.SITE_URL, "unsubscribe", token);
        await sendEmail(env, email, digest.subject, digest.text + "\n\n이메일 주소 삭제\n" + link,
          "weekly/" + digest.week + "/" + token);
        await env.DB.prepare(
          "UPDATE subscribers SET last_digest_week = ? WHERE unsubscribe_token = ? AND last_digest_week < ?",
        ).bind(digest.week, token, digest.week).run();
      } catch {
        failures += 1;
      }
      await new Promise(resolve => setTimeout(resolve, 550));
    }
    cursor = batch.at(-1).email;
  }
  if (failures > 0) throw new Error("Weekly email delivery failed for " + failures + " recipients");
}

export default {
  fetch: handleRequest,
  async scheduled(controller, env) {
    await sendWeeklyDigest(controller.scheduledTime, env);
  },
};
