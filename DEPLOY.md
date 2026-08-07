## Switching to Live Stripe (when ready)

1. Open `.streamlit/secrets.toml`
2. Replace `sk_test_...` with `sk_live_...`
3. Replace the 3 test price IDs with the 3 live price IDs from your live Stripe dashboard
4. Replace the webhook secret with a live one (run `stripe listen` against your live endpoint)

---

## Deploying to Railway

### 1. Push to GitHub
```bash
git add .
git commit -m "Add Gemini AI + coin payment system"
git push
```

### 2. Deploy on Railway
1. Go to https://railway.app and sign in with GitHub
2. Click **New Project → Deploy from GitHub repo**
3. Select your ThinkTank repo
4. Railway will auto-detect Python and deploy

### 3. Set environment variables on Railway
In your Railway project → **Variables** tab, add each secret:
```
GEMINI_API_KEY        = your key
STRIPE_SECRET_KEY     = sk_live_...
STRIPE_WEBHOOK_SECRET = whsec_...  (live webhook secret)
STRIPE_PRICE_STARTER  = price_...
STRIPE_PRICE_STANDARD = price_...
STRIPE_PRICE_PRO      = price_...
```

### 4. Update Stripe webhook URL
Once Railway gives you a public URL (e.g. `https://thinktank.up.railway.app`):
1. Go to Stripe Dashboard → Developers → Webhooks
2. Add endpoint: `https://thinktank.up.railway.app/webhook`
3. Event: `checkout.session.completed`
4. Copy the new webhook secret → update Railway variable

### 5. Update success/cancel URLs in app.py
Find these lines in app.py (~line 703):
```python
success_url="http://localhost:8501?purchase=success..."
cancel_url="http://localhost:8501?purchase=cancelled"
```
Change `http://localhost:8501` to your Railway URL.

---

## What users experience

1. Visit your Railway URL
2. Go to 💳 Buy Coins → select package → pay via Stripe
3. Coins are credited → go to 💬 Ask → each message costs 1 coin
4. When out of coins → prompted to buy more
