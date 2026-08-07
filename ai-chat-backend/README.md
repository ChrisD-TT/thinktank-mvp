# AI Chat Backend — Setup Guide

## What this is
A Node.js backend that:
- **Proxies all AI calls** — your API key is never in the browser
- **Rate-limits users** — max 30 requests/minute per IP
- **Charges coins per message** — users buy coins via Stripe before chatting
- **Stripe handles all payments** — money goes to YOUR Stripe account, not your personal bank card

---

## Prerequisites
- Node.js 18+
- A free [Google AI Studio](https://aistudio.google.com/app/apikey) account (Gemini key — free)
- A [Stripe](https://stripe.com) account (free to create)

---

## Step 1 — Install

```bash
cd ai-chat-backend
npm install
```

---

## Step 2 — Create your .env file

```bash
cp .env.example .env
```

Then fill in each value:

### AI_API_KEY (Free)
1. Go to https://aistudio.google.com/app/apikey
2. Click "Create API Key"
3. Paste it as `AI_API_KEY=...`

### Stripe Keys
1. Go to https://dashboard.stripe.com/apikeys
2. Copy your **Secret key** (`sk_live_...` for live, `sk_test_...` for testing)
3. Paste as `STRIPE_SECRET_KEY=...`

### Stripe Products (Coin Packages)
1. Go to https://dashboard.stripe.com/products
2. Create 3 products:
   - **Starter** — one-time price $1.99
   - **Standard** — one-time price $4.99
   - **Pro** — one-time price $9.99
3. Click each product → copy the **Price ID** (`price_...`)
4. Paste as `STRIPE_PRICE_STARTER=price_...` etc.

### Stripe Webhook Secret
1. Go to https://dashboard.stripe.com/webhooks
2. Click "Add endpoint"
3. URL: `https://yourdomain.com/api/webhook`
4. Event: `checkout.session.completed`
5. Copy the **Signing secret** (`whsec_...`)
6. Paste as `STRIPE_WEBHOOK_SECRET=...`

> **For local testing:** use `stripe listen --forward-to localhost:3001/api/webhook`
> (install Stripe CLI: https://stripe.com/docs/stripe-cli)

---

## Step 3 — Start the backend

```bash
npm start
# or for auto-reload during development:
npm run dev
```

The server runs on http://localhost:3001

---

## Step 4 — Open the chat UI

Open `chat.html` in your browser (or serve it from a web server).

> The `const API = 'http://localhost:3001'` line at the top of `chat.html` must match your
> backend URL. Change it to your deployed URL before going live.

---

## How money flows (you never touch card data)

```
User clicks "Buy Coins"
    → Your backend creates a Stripe Checkout Session
    → User is sent to Stripe's hosted payment page
    → User pays Stripe with their card
    → Stripe sends a webhook to /api/webhook
    → Your backend credits coins to the user
    → Stripe deposits money into YOUR Stripe account
    → You withdraw from Stripe to your bank on a schedule
```

You never handle raw card numbers. Stripe is PCI-compliant so you don't have to be.

---

## Coin pricing (edit in server.js)

| Package  | Coins | Price |
|----------|-------|-------|
| Starter  | 50    | $1.99 |
| Standard | 200   | $4.99 |
| Pro      | 600   | $9.99 |

To change pricing: update Stripe product prices AND the `COIN_PACKAGES` array in `server.js`.

---

## Rate limits
- 30 AI requests per minute per IP address
- 1 coin per message (configurable in the `spendCoins` call in server.js)
- Users with 0 coins get a 402 response and the shop opens automatically

---

## Files

| File        | Purpose                              |
|-------------|--------------------------------------|
| server.js   | Express backend — all API routes     |
| db.js       | SQLite coin ledger (auto-created)    |
| chat.html   | Frontend chat UI                     |
| .env        | Your secrets (never commit this)     |
| coins.sqlite| User balances (auto-created on start)|

---

## Deploying to production

Recommended: [Railway](https://railway.app) or [Render](https://render.com) — both have free tiers.

1. Push this folder to a GitHub repo
2. Connect it to Railway/Render
3. Add all `.env` variables in the dashboard
4. Update `FRONTEND_URL` to your real domain
5. Update `const API = '...'` in `chat.html` to your backend URL
6. Update the Stripe webhook endpoint URL in Stripe dashboard
