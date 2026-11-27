import assert from "node:assert/strict";
import test from "node:test";
import worker from "./worker.mjs";

test("reads the Gmail acknowledgement without forwarding the mail credential", async (context) => {
  const origin = "https://movies.example.com";
  const relay = "https://script.google.com/macros/s/test/exec";
  const acknowledgement = "https://script.googleusercontent.com/macros/echo?test=1";
  const secret = "a".repeat(64);
  const token = "b".repeat(64);
  let storedDelivery = false;
  const fetchMock = context.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(options.redirect, "manual");
    if (url === relay) {
      assert.equal(JSON.parse(options.body).key, secret);
      return new Response(null, { status: 302, headers: { Location: acknowledgement } });
    }
    assert.equal(String(url), acknowledgement);
    assert.equal(options.body, undefined);
    return Response.json({ ok: true });
  });
  const env = {
    SITE_URL: origin + "/",
    GMAIL_RELAY_URL: relay,
    GMAIL_RELAY_SECRET: secret,
    EMAIL_REQUEST_LIMIT: { async limit() { return { success: true }; } },
    DB: {
      prepare(statement) {
        return {
          bind(...values) {
            return {
              async first() { return { token }; },
              async run() {
                assert.match(statement, /^UPDATE pending_subscriptions SET mail_sent = 1/);
                assert.deepEqual(values, [token]);
                storedDelivery = true;
              },
            };
          },
        };
      },
    },
  };

  const response = await worker.fetch(new Request("https://mail.example.com/request", {
    method: "POST",
    headers: { Origin: origin, "Content-Type": "application/json" },
    body: JSON.stringify({ action: "subscribe", email: "reader@example.com" }),
  }), env);

  assert.equal(response.status, 204);
  assert.equal(fetchMock.mock.callCount(), 2);
  assert.equal(storedDelivery, true);
});
