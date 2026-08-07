// db.js — SQLite ledger using Node.js built-in sqlite (Node 22+, no install needed)
import { DatabaseSync } from 'node:sqlite';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const db = new DatabaseSync(join(__dirname, 'coins.sqlite'));

// ── Schema ─────────────────────────────────────────────────────────────────
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    coins       INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL DEFAULT (unixepoch())
  );

  CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL,
    type            TEXT NOT NULL,
    amount          INTEGER NOT NULL,
    stripe_session  TEXT,
    created_at      INTEGER NOT NULL DEFAULT (unixepoch())
  );
`);

// ── Helpers ─────────────────────────────────────────────────────────────────

export function getOrCreateUser(userId) {
  let user = db.prepare('SELECT id, coins FROM users WHERE id = ?').get(userId);
  if (!user) {
    db.prepare('INSERT INTO users (id, coins) VALUES (?, 0)').run(userId);
    user = { id: userId, coins: 0 };
  }
  return user;
}

export function getBalance(userId) {
  const row = db.prepare('SELECT coins FROM users WHERE id = ?').get(userId);
  return row ? row.coins : 0;
}

export function spendCoins(userId, amount = 1) {
  const row = db.prepare('SELECT coins FROM users WHERE id = ?').get(userId);
  if (!row || row.coins < amount) return false;
  db.prepare('UPDATE users SET coins = coins - ? WHERE id = ?').run(amount, userId);
  db.prepare(`INSERT INTO transactions (user_id, type, amount) VALUES (?, 'spend', ?)`)
    .run(userId, -amount);
  return true;
}

export function creditCoins(userId, amount, stripeSession) {
  // Idempotency: ignore duplicate webhook deliveries
  const already = db
    .prepare('SELECT id FROM transactions WHERE stripe_session = ?')
    .get(stripeSession);
  if (already) return;

  getOrCreateUser(userId);
  db.prepare('UPDATE users SET coins = coins + ? WHERE id = ?').run(amount, userId);
  db.prepare(
    `INSERT INTO transactions (user_id, type, amount, stripe_session) VALUES (?, 'purchase', ?, ?)`
  ).run(userId, amount, stripeSession);
}
