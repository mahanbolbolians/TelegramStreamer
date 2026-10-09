# 🚀 TelegramStreamer + Cloudflare High-Speed Deployment Guide

This guide explains how to set up the **TelegramStreamer + Cloudflare Edge Gateway** architecture to download Telegram files (up to 4 GB) at **full ISP wire speed without needing a VPN**, achieving speeds comparable to a local Iranian VPS.

---

## 🏗️ Architecture Blueprint

```text
[ Telegram DC4 (Amsterdam) ]
             ▲
             │ (High-Speed MTProto Binary Stream)
             ▼
   [ Railway (Amsterdam) ]
             ▲
             │ (HTTP 206 Partial Content Stream)
             ▼
[ Cloudflare Worker Gateway (Custom Domain) ]
             ▲
             │ (8–16 Parallel ADM Threads)
             ▼
  [ Phone / ADM (No VPN Required) ]
```

---

## Step 1: Get Your Telegram Credentials (Takes 2 Minutes)

You need 4 pieces of information from Telegram:

### A. Create Your Bot
1. Open Telegram and search for **[@BotFather](https://t.me/BotFather)**.
2. Send `/newbot`.
3. Give it a name and username ending in `bot` (e.g. `MyFastDownloader_bot`).
4. Copy the **HTTP API Token** (e.g. `1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ`).

### B. Get Your API ID & Hash
1. Open **[my.telegram.org](https://my.telegram.org)** in your browser.
2. Log in with your phone number and Telegram verification code.
3. Click **API development tools**.
4. Create an application (App title and short name can be anything).
5. Copy **`App api_id`** and **`App api_hash`**.

### C. Get Your Numeric User ID (Whitelist)
1. Search for **[@userinfobot](https://t.me/userinfobot)** in Telegram and click **Start**.
2. Copy your numeric **Id** (e.g. `987654321`). This prevents unauthorized people from consuming your server bandwidth.

---

## Step 2: Fork the Repository

1. Open: **https://github.com/mahanbolbolians/TelegramStreamer**
2. Click **Fork** (top-right) → **Create Fork** under your own GitHub account.

---

## Step 3: Deploy to Railway (in Amsterdam)

1. Open **[railway.com](https://railway.com)** and log in with your GitHub account.
2. Click **+ New Project** → **Deploy from GitHub repo**.
3. Select your forked `TelegramStreamer` repository.
4. Click on the newly created service box to open its settings:
   * Go to **Settings** → **General / Service Settings**.
   * Under **Region**, select **Europe (Amsterdam / Netherlands)**.  
     *(CRITICAL: Telegram's core European data center is in Amsterdam. Selecting Amsterdam gives you near-zero latency and maximum ingest speed).*
   * Under **Networking**, click **Generate Domain** (e.g. `https://web-production-xxxx.up.railway.app`). Save this URL.
5. Go to the **Variables** tab and add:
   ```env
   TELEGRAM_API_ID=your_api_id
   TELEGRAM_API_HASH=your_api_hash
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_CHAT_IDS=your_user_id
   ```
6. Click **Deploy**.

---

## Step 4: Deploy the Cloudflare Worker Gateway (Takes 1 Minute)

1. Open **[dash.cloudflare.com](https://dash.cloudflare.com)** (Free account, no credit card required).
2. On the left sidebar, click **Workers & Pages** → **Create application** → **Create Worker**.
3. Name it (e.g. `telegram-streamer-gateway`) and click **Deploy**.
4. Click **Edit code** and paste the contents of `cloudflare-worker/worker.js`:

```javascript
export default {
  async fetch(request, env) {
    const backendBase = (env.RAILWAY_URL || "").trim().replace(/\/+$/, "");
    if (!backendBase) {
      return new Response("Error: RAILWAY_URL environment variable is not configured.", { status: 500 });
    }

    const clientUrl = new URL(request.url);
    const targetUrl = new URL(clientUrl.pathname + clientUrl.search, backendBase);

    const forwardHeaders = new Headers(request.headers);
    forwardHeaders.set("Host", targetUrl.host);
    forwardHeaders.delete("cf-connecting-ip");
    forwardHeaders.delete("cf-ipcountry");
    forwardHeaders.delete("cf-ray");
    forwardHeaders.delete("cf-visitor");

    try {
      const upstreamResponse = await fetch(targetUrl.toString(), {
        method: request.method,
        headers: forwardHeaders,
        redirect: "follow",
      });

      const responseHeaders = new Headers(upstreamResponse.headers);
      responseHeaders.set("Access-Control-Allow-Origin", "*");
      responseHeaders.set("Access-Control-Allow-Headers", "*");
      responseHeaders.set("Access-Control-Expose-Headers", "Content-Range, Accept-Ranges, Content-Length, Content-Disposition");

      return new Response(upstreamResponse.body, {
        status: upstreamResponse.status,
        statusText: upstreamResponse.statusText,
        headers: responseHeaders,
      });
    } catch (err) {
      return new Response(`Gateway error: ${err.message}`, { status: 502 });
    }
  }
};
```
5. Click **Save and Deploy**.
6. Go to **Settings** → **Variables and Secrets** → **Add Variable**:
   * **Name:** `RAILWAY_URL`
   * **Value:** Your Railway URL from Step 3 (e.g. `https://web-production-xxxx.up.railway.app`)
7. Click **Deploy**.

---

## Step 5: Attach a Custom Domain (Bypasses Censorship Without VPN)

The default `*.workers.dev` domain is blocked in Iran. Adding a custom domain routes traffic through standard Cloudflare CDN Anycast IPs that work without a VPN:

1. Inside your Cloudflare Worker page, go to **Settings** → **Domains & Routes**.
2. Click **Add Custom Domain**.
3. Type your subdomain (e.g. `dl.yourdomain.com`).
4. Click **Add Custom Domain** (Cloudflare creates the DNS record and SSL certificate in ~30 seconds).

---

## Step 6: Configure the Bot to Return Cloudflare Links

1. Open your project on **[railway.com](https://railway.com)**.
2. Go to your service → **Variables** tab.
3. Add a new variable:
   * **Key:** `CUSTOM_DOMAIN`
   * **Value:** `https://dl.yourdomain.com` *(your Cloudflare custom domain)*
4. Click **Deploy**.

---

## Step 7: Android Phone Optimization (Crucial for Iran)

To guarantee that your phone resolves the domain without ISP DNS UDP-53 timeouts:

1. Open Android **Settings** → **Network & Internet** (or **Connections** → **More connection settings**).
2. Tap **Private DNS**.
3. Select **Private DNS provider hostname** and enter:
   ```text
   dns.google
   ```
4. In **ADM (Advanced Download Manager)**:
   * Settings → Downloading → Set **Threads** to **8** or **16**.

---

## ⚡ Features Included

* **Instant Link Generation:** Forwards files up to **4.0 GB** with 0-second wait time.
* **HTTP 206 Multi-threading:** Full chunked streaming with parallel connections in ADM.
* **On-Demand 720p HD Compression:** An inline button (`⚡ Compress to 720p HD`) automatically shrinks large videos by ~65% using high-speed FFmpeg with live progress bars.
* **Auto-Cleanup:** Ephemeral storage is purged automatically every 24 hours so disk space never fills up.
