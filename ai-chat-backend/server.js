// server.js — AI Chat Backend
// Routes: /api/chat, /api/purchase, /api/webhook, /api/balance
import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import rateLimit from 'express-rate-limit';
import Stripe from 'stripe';
import { v4 as uuidv4 } from 'uuid';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { getOrCreateUser, getBalance, spendCoins, creditCoins } from './db.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

// ── Env validation — only AI_API_KEY is required to start ────────────────────
if (!process.env.AI_API_KEY) {
  console.error('Missing required env var: AI_API_KEY');
  process.exit(1);
}

// Stripe is optional until purchase routes are used
const stripeEnabled = !!(process.env.STRIPE_SECRET_KEY && process.env.STRIPE_WEBHOOK_SECRET);
const stripe = stripeEnabled
  ? new Stripe(process.env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' })
  : null;

const app = express();

// ── Coin packages users can buy ───────────────────────────────────────────────
// Edit these to change pricing. price_id comes from your Stripe dashboard.
const COIN_PACKAGES = [
  { id: 'starter',  coins: 40,   price_usd: 399,  stripe_price_id: process.env.STRIPE_PRICE_STARTER  },
  { id: 'standard', coins: 125,  price_usd: 799,  stripe_price_id: process.env.STRIPE_PRICE_STANDARD },
  { id: 'pro',      coins: 450,  price_usd: 1499, stripe_price_id: process.env.STRIPE_PRICE_PRO      },
];

// ── Static files — serve chat.html at http://localhost:3001/ ─────────────────
app.use(express.static(__dirname, { index: 'chat.html' }));

// ── Middleware ─────────────────────────────────────────────────────────────────
// Allow both file:// and http://localhost origins during development
app.use(cors({
  origin: (origin, cb) => cb(null, true),
  credentials: true,
}));

// Stripe webhook needs raw body — mount BEFORE express.json()
app.post(
  '/api/webhook',
  express.raw({ type: 'application/json' }),
  handleStripeWebhook
);

app.use(express.json());

// Cookie-based user identity (no login required)
app.use((req, _res, next) => {
  // Read or mint a session id
  let userId = null;
  const cookieHeader = req.headers.cookie || '';
  const match = cookieHeader.match(/uid=([a-f0-9-]{36})/);
  if (match) userId = match[1];
  if (!userId) userId = uuidv4();
  req.userId = userId;
  getOrCreateUser(userId);
  next();
});

// Helper: set the uid cookie on every response
function setUserCookie(res, userId) {
  res.setHeader(
    'Set-Cookie',
    `uid=${userId}; Path=/; Max-Age=${60 * 60 * 24 * 365}; HttpOnly; SameSite=Lax`
  );
}

// ── Rate limiter: max 30 requests / minute / IP (separate from coin cost) ─────
const chatLimiter = rateLimit({
  windowMs: 60_000,
  max: 30,
  message: { error: 'Too many requests. Slow down.' },
});

// ── GET /api/balance ──────────────────────────────────────────────────────────
app.get('/api/balance', (req, res) => {
  setUserCookie(res, req.userId);
  res.json({ userId: req.userId, coins: getBalance(req.userId) });
});

// ── GET /api/packages ─────────────────────────────────────────────────────────
app.get('/api/packages', (_req, res) => {
  res.json(
    COIN_PACKAGES.map(({ id, coins, price_usd }) => ({ id, coins, price_usd }))
  );
});

// ── POST /api/admin/grant — give test coins (dev only, remove in production) ──
app.post('/api/admin/grant', (req, res) => {
  const { amount = 50 } = req.body;
  creditCoins(req.userId, amount, `admin-grant-${Date.now()}-${req.userId}`);
  res.json({ ok: true, coins: getBalance(req.userId) });
});

// ── POST /api/chat ────────────────────────────────────────────────────────────
// Body: { message: string }
// Cost: 1 coin per message
app.post('/api/chat', chatLimiter, async (req, res) => {
  setUserCookie(res, req.userId);

  const { message } = req.body;
  if (!message || typeof message !== 'string' || message.trim().length === 0) {
    return res.status(400).json({ error: 'message is required' });
  }
  if (message.length > 2000) {
    return res.status(400).json({ error: 'Message too long (max 2000 chars)' });
  }

  // Check + deduct coins BEFORE calling the AI
  const spent = spendCoins(req.userId, 1);
  if (!spent) {
    return res.status(402).json({
      error: 'Not enough coins',
      coins: getBalance(req.userId),
    });
  }

  try {
    // ── Gemini API call (key stays server-side) ──────────────────────────────
    const aiRes = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${process.env.AI_API_KEY}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: message.trim() }] }],
          generationConfig: { maxOutputTokens: 800 },
        }),
      }
    );

    if (!aiRes.ok) {
      const errText = await aiRes.text();
      console.error('AI API error:', errText);
      // Refund the coin if the AI call failed
      creditCoins(req.userId, 1, `refund-${Date.now()}-${req.userId}`);
      return res.status(502).json({ error: 'AI service unavailable. Coin refunded.' });
    }

    const data = await aiRes.json();
    const reply =
      data?.candidates?.[0]?.content?.parts?.[0]?.text ?? '(no response)';

    res.json({ reply, coins: getBalance(req.userId) });
  } catch (err) {
    console.error('Chat error:', err);
    creditCoins(req.userId, 1, `refund-${Date.now()}-${req.userId}`);
    res.status(500).json({ error: 'Internal server error. Coin refunded.' });
  }
});

// ── POST /api/purchase ────────────────────────────────────────────────────────
// Body: { packageId: 'starter' | 'standard' | 'pro' }
// Creates a Stripe Checkout session — user pays Stripe, never you directly
app.post('/api/purchase', async (req, res) => {
  setUserCookie(res, req.userId);

  if (!stripeEnabled) {
    return res.status(503).json({ error: 'Payments not configured yet. Add Stripe keys to .env to enable.' });
  }

  const { packageId } = req.body;
  const pkg = COIN_PACKAGES.find((p) => p.id === packageId);
  if (!pkg) {
    return res.status(400).json({ error: 'Invalid package' });
  }
  if (!pkg.stripe_price_id) {
    return res
      .status(500)
      .json({ error: `Stripe price ID for "${packageId}" not configured` });
  }

  try {
    const session = await stripe.checkout.sessions.create({
      mode: 'payment',
      line_items: [{ price: pkg.stripe_price_id, quantity: 1 }],
      success_url: `${process.env.FRONTEND_URL}?purchase=success&session_id={CHECKOUT_SESSION_ID}`,
      cancel_url:  `${process.env.FRONTEND_URL}?purchase=cancelled`,
      metadata: {
        userId:  req.userId,
        coins:   String(pkg.coins),
        package: pkg.id,
      },
    });

    res.json({ url: session.url });
  } catch (err) {
    console.error('Stripe error:', err);
    res.status(500).json({ error: 'Failed to create checkout session' });
  }
});

// ── POST /api/webhook (Stripe) ────────────────────────────────────────────────
// Stripe calls this after payment. Coins are ONLY credited here, never before.
async function handleStripeWebhook(req, res) {
  const sig = req.headers['stripe-signature'];
  let event;

  try {
    event = stripe.webhooks.constructEvent(
      req.body,
      sig,
      process.env.STRIPE_WEBHOOK_SECRET
    );
  } catch (err) {
    console.error('Webhook signature failed:', err.message);
    return res.status(400).send(`Webhook Error: ${err.message}`);
  }

  if (event.type === 'checkout.session.completed') {
    const session = event.data.object;
    const { userId, coins } = session.metadata;

    if (userId && coins) {
      creditCoins(userId, parseInt(coins, 10), session.id);
      console.log(`Credited ${coins} coins to user ${userId} (session ${session.id})`);
    }
  }

  res.json({ received: true });
}

// ── Start ─────────────────────────────────────────────────────────────────────
const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  console.log(`AI Chat Backend running on http://localhost:${PORT}`);
});
