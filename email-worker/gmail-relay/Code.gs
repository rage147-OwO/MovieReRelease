const RELAY_KEY_SHA256 = "REPLACE_WITH_RELAY_KEY_SHA256";
const HEX_SHA256 = /^[a-f0-9]{64}$/;
const SINGLE_EMAIL = /^[a-z0-9.!#$%&'*+\/=?^_~-]+@(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i;
const ONE_DAY = 24 * 60 * 60 * 1000;
const DELIVERY_PREFIX = "delivery:";

function response(ok) {
  return ContentService.createTextOutput(JSON.stringify({ ok }))
    .setMimeType(ContentService.MimeType.JSON);
}

function authenticated(key) {
  if (typeof key !== "string" || !HEX_SHA256.test(key) || !HEX_SHA256.test(RELAY_KEY_SHA256)) {
    return false;
  }
  const digest = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, key, Utilities.Charset.UTF_8);
  const actual = digest.map(byte => (byte & 255).toString(16).padStart(2, "0")).join("");
  let difference = 0;
  for (let index = 0; index < actual.length; index += 1) {
    difference |= actual.charCodeAt(index) ^ RELAY_KEY_SHA256.charCodeAt(index);
  }
  return difference === 0;
}

function doGet() {
  return response(false);
}

function doPost(event) {
  try {
    const body = event?.postData?.contents;
    if (typeof body !== "string" || body.length > 120000) return response(false);
    const data = JSON.parse(body);
    if (!authenticated(data?.key)) return response(false);
    if (!HEX_SHA256.test(data.requestId || "") ||
        typeof data.email !== "string" || data.email.length > 254 || !SINGLE_EMAIL.test(data.email) ||
        typeof data.subject !== "string" || !data.subject || data.subject.length > 180 || /[\r\n]/.test(data.subject) ||
        typeof data.text !== "string" || !data.text || data.text.length > 100000) {
      return response(false);
    }

    const lock = LockService.getScriptLock();
    if (!lock.tryLock(5000)) return response(false);
    try {
      const properties = PropertiesService.getScriptProperties();
      const now = Date.now();
      const deliveryKey = DELIVERY_PREFIX + data.requestId;
      if (Number(properties.getProperty(deliveryKey)) >= now - ONE_DAY) return response(true);
      if (MailApp.getRemainingDailyQuota() < 1) return response(false);
      if (Number(properties.getProperty("deliveryCleanup")) < now - ONE_DAY) {
        for (const [key, sentAt] of Object.entries(properties.getProperties())) {
          if (key.startsWith(DELIVERY_PREFIX) && Number(sentAt) < now - ONE_DAY) {
            properties.deleteProperty(key);
          }
        }
        properties.setProperty("deliveryCleanup", String(now));
      }
      MailApp.sendEmail({ to: data.email, subject: data.subject, body: data.text, name: "재개봉 알리미" });
      properties.setProperty(deliveryKey, String(now));
      return response(true);
    } finally {
      lock.releaseLock();
    }
  } catch {
    return response(false);
  }
}
