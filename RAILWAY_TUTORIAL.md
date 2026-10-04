# 🚀 TelegramStreamer — Complete Railway Deployment Guide

This guide explains how to set up and deploy **TelegramStreamer** to run **24/7 in the cloud for free** on Railway. 

Once deployed:
- No PC or laptop needs to stay turned on.
- No VPN is required on your PC.
- You can forward any video/file (up to 2 GB) to your bot in Telegram and download it at full speed on your phone using **ADM (Android)** or on your computer using **IDM / Browser**.

---

## Step 1: Get Your Telegram Credentials (Takes 2 Minutes)

You need 4 pieces of information from Telegram:

### A. Create Your Bot & Get the Bot Token
1. Open Telegram and search for **[@BotFather](https://t.me/BotFather)**.
2. Send the command: `/newbot`
3. Enter a display name for your bot (e.g., `My Streamer Bot`).
4. Enter a username ending in `bot` (e.g., `MyStreamer123_bot`).
5. BotFather will reply with an **HTTP API Token** (looks like: `1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ`).
   - 📌 *Save this token.*

### B. Get Your API ID & API Hash
1. Go to **[my.telegram.org](https://my.telegram.org)** in your web browser.
2. Log in with your Telegram phone number (enter the confirmation code sent to your Telegram app).
3. Click on **API development tools**.
4. In **App title** and **Short name**, type anything (e.g. `Streamer`). Click **Create application**.
5. You will see:
   - **`App api_id`**: A number (e.g. `12345678`)
   - **`App api_hash`**: A string of letters and numbers (e.g. `a1b2c3d4e5f67890abcdef1234567890`)
   - 📌 *Save both of these.*

### C. Get Your Numeric Telegram User ID
*(This acts as a whitelist so ONLY you can use your bot and no strangers can consume your bandwidth.)*
1. In Telegram, search for **[@userinfobot](https://t.me/userinfobot)** and click **Start**.
2. It will reply with your numeric **Id** (e.g. `987654321`).
   - 📌 *Save this number.*

---

## Step 2: Fork the GitHub Repository

1. Open the repository on GitHub:
   👉 **https://github.com/mahanbolbolians/TelegramStreamer**
2. Click the **Fork** button near the top right corner.
3. Click **Create Fork**. 
   *(You now have your own copy of the code under your own GitHub account).*

---

## Step 3: Create a Project on Railway

1. Go to **[railway.com](https://railway.com)**.
2. Click **Login** and select **Login with GitHub** (use the same GitHub account where you forked the repo).
3. On your Railway dashboard, click **+ New Project**.
4. Select **Deploy from GitHub repo**.
5. Choose **`TelegramStreamer`** from the list of repositories.
6. Click **Deploy Now**.

---

## Step 4: Add Your Telegram Variables (Crucial)

1. Click on the newly created service box (named `web` or `TelegramStreamer`) to open its panel.
2. Go to the **Variables** tab.
3. Click **+ New Variable** (or click **Raw Editor** at the top right) and paste the following 4 lines:

```env
TELEGRAM_API_ID=YOUR_API_ID
TELEGRAM_API_HASH=YOUR_API_HASH
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_CHAT_IDS=YOUR_NUMERIC_USER_ID
```

### 💡 Example (Replace with your actual keys from Step 1):
```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=a1b2c3d4e5f67890abcdef1234567890
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_CHAT_IDS=987654321
```

4. Click **Save** / **Deploy**.

---

## Step 5: Generate Public Domain & Maximize Speed

1. While inside the service panel, click the **Settings** tab.
2. **Generate Public Domain**:
   - Scroll down to the **Networking** section.
   - Click **Generate Domain**. Railway will create a public web address (e.g., `web-production-xxxx.up.railway.app`).
3. **Change Region to Europe (Amsterdam)**:
   - In the **Settings** tab, scroll to **General / Service Settings**.
   - Under **Region**, select **Europe (Amsterdam / Netherlands)**.
   - *(Why? Telegram's primary media servers for the Middle East and Europe are physically located in Amsterdam. This gives you the lowest latency and maximum download speed!)*
4. Click **Redeploy** if prompted.

---

## Step 6: Test & Start Downloading!

1. Wait about 30–60 seconds until Railway shows a **green checkmark (Active)**.
2. Open Telegram and message your bot.
3. Send or forward any video, movie, or file (up to 2 GB) to the bot.
4. The bot will instantly reply with a direct download link!
5. **How to download:**
   - **On Android (ADM)**: Copy the link, open **Advanced Download Manager (ADM)**, tap **+**, paste the link, and hit **Start**.
   - **On PC (IDM / Browser)**: Paste the link into **Internet Download Manager (IDM)** or your browser address bar.

---

## 💡 Good to Know:
- **Zero Disk Usage**: The bot streams directly through RAM chunk-by-chunk. It does not store huge files on the server.
- **Bandwidth**: Railway's free trial provides plenty of bandwidth (roughly 70–80 GB of downloads per month).
- **Security**: Because of `TELEGRAM_CHAT_IDS`, only your authorized user ID can interact with the bot.
