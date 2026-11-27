CREATE TABLE subscribers (
    email TEXT PRIMARY KEY,
    unsubscribe_token TEXT NOT NULL UNIQUE,
    last_remove_request INTEGER NOT NULL DEFAULT 0,
    last_digest_week TEXT NOT NULL DEFAULT ''
);

CREATE TABLE pending_subscriptions (
    email TEXT PRIMARY KEY,
    token TEXT NOT NULL UNIQUE,
    requested_at INTEGER NOT NULL
);
