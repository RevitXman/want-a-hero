# Want-A-Hero Bot

A Discord bot for tracking Age of Empires Mobile hero-unlock medal requests.  
Runs on Ubuntu EC2, stores data in SQLite, and optionally syncs to Google Sheets (one tab per MGE week, Monday–Sunday UTC).

---

## Commands

### Player Commands

| Command | Description |
|---|---|
| `/wantahero` | Submit a hero medal request. Fields: **Game Name** (text), **Alliance** (dropdown), **Hero** (dropdown), **Medals Needed** (1–10 dropdown) |

### Admin Commands

These require the **Hero Admin** Discord role or Server Administrator permission.

| Command | Description |
|---|---|
| `/hero_report [week_offset]` | List all requests for a week (0 = current, -1 = last week). Reads from Google Sheets when enabled, falls back to SQLite. |
| `/hero_delete request_id` | Delete one request by ID |
| `/hero_update request_id [fields]` | Edit any field on an existing request |
| `/hero_clear confirm:YES` | Wipe **all** requests from the database |
| `/hero_sync` | Force Discord to re-register all slash commands immediately |

### Alliance Management

| Command | Description |
|---|---|
| `/hero_alliance list` | Show all alliances in the dropdown |
| `/hero_alliance add name` | Add a new alliance (Hero Admin only) |
| `/hero_alliance remove name` | Remove an alliance (Hero Admin only) |

Default alliances: `K27`, `S27`, `T27`, `T2P`

### Hero Management

| Command | Description |
|---|---|
| `/hero_manage list` | Show all heroes in the dropdown |
| `/hero_manage add name` | Add a new hero (Hero Admin only) |
| `/hero_manage remove name` | Remove a hero (Hero Admin only) |

Alliance and hero lists are stored in `data/alliances.json` and `data/heroes.json` and survive bot restarts.

---

## Google Sheets Column Layout

Each weekly tab (named `Week YYYY-MM-DD`) uses this column layout:

| Column | Field | Notes |
|---|---|---|
| A | Request ID | Auto-filled by bot |
| B | Discord User | Auto-filled by bot |
| C | Game Name | Auto-filled by bot |
| D | Alliance | Auto-filled by bot |
| E | Hero | Auto-filled by bot |
| F | Medals Needed | Auto-filled by bot |
| G | Selected for MGE | **Filled manually by admins** |
| H | Submitted At (UTC) | Auto-filled by bot |

The **Selected for MGE** column is intentionally left blank by the bot — admins mark selections manually after reviewing requests each week.

---

## Quick-Start (Ubuntu EC2)

### 1 — Launch an EC2 instance

- **AMI**: Ubuntu 22.04 LTS (or 24.04)
- **Instance type**: t3.micro is plenty
- **Security group**: outbound HTTPS (443) required; no inbound ports needed
- **Key pair**: keep your `.pem` safe

### 2 — SSH in and clone the repo

**From Linux/Mac or Windows PowerShell:**
```bash
ssh -i your-key.pem ubuntu@<your-ec2-ip>
```

On Windows, if you get a "permissions too open" error on your key:
```powershell
icacls "C:\path\to\your-key.pem" /inheritance:r /grant:r "$($env:USERNAME):(R)"
```

Once connected:
```bash
git clone https://github.com/your-org/want-a-hero-bot.git
cd want-a-hero-bot
```

### 3 — Run the setup script

```bash
chmod +x setup.sh
./setup.sh
```

This installs Python, creates a dedicated `herobot` system user, sets up `/opt/wantahero`, installs the Python venv, and registers the systemd service.

### 4 — Create your Discord bot

1. Go to <https://discord.com/developers/applications> → **New Application**
2. Name it (e.g. *Want-A-Hero*)
3. **Bot** tab → **Reset Token** → copy the **Token**
4. On the same page, enable **Message Content Intent** under Privileged Gateway Intents
5. **OAuth2 → URL Generator**: select scopes `bot` + `applications.commands`; permissions: `Send Messages`, `Embed Links`
6. Open the generated URL and invite the bot to your server
7. In your server, create a role named exactly **`Hero Admin`** and assign it to your officers

### 5 — Get your Guild (Server) ID

Enable Developer Mode in Discord: **Settings → Advanced → Developer Mode**.  
Then right-click your server icon → **Copy Server ID**.

This is your `GUILD_ID` — setting it makes slash commands sync instantly instead of waiting up to an hour.

### 6 — Configure environment variables

```bash
sudo nano /opt/wantahero/.env
```

Fill in at minimum:

```
DISCORD_TOKEN=your_discord_bot_token_here
ADMIN_ROLE_NAME=Hero Admin
GUILD_ID=your_server_id_here
```

### 7 — Start the bot

```bash
sudo systemctl start wantahero
sudo systemctl status wantahero        # should show "active (running)"
sudo journalctl -u wantahero -f        # live logs
```

The service restarts automatically on failure and on EC2 reboot.

---

## Google Sheets Setup (Optional)

When enabled, every `/wantahero` submission appends a row to your spreadsheet. Tabs are named `Week YYYY-MM-DD` (the Monday of that MGE week) and are created automatically.

### Step 1 — Create a Google Cloud project

1. Go to <https://console.cloud.google.com/> → **New Project** (e.g. *WantAHeroBot*)
2. Select your new project

### Step 2 — Enable the Sheets & Drive APIs

1. **APIs & Services → Library**
2. Search **Google Sheets API** → Enable
3. Search **Google Drive API** → Enable

### Step 3 — Create a Service Account

1. **APIs & Services → Credentials → Create Credentials → Service Account**
2. Name it (e.g. `wantahero-bot`), click **Done**
3. Click the service account → **Keys** tab → **Add Key → Create new key → JSON**
4. A `.json` file downloads — this is your credentials file

### Step 4 — Share the spreadsheet with the service account

1. Create a new Google Sheet
2. Copy the **spreadsheet ID** from the URL:  
   `https://docs.google.com/spreadsheets/d/THIS_PART_HERE/edit`
3. Click **Share** and add the service account email (e.g. `wantahero-bot@your-project.iam.gserviceaccount.com`) as an **Editor**

### Step 5 — Upload credentials to EC2

**From PowerShell or terminal:**
```powershell
scp -i "C:\path\to\your-key.pem" service_account.json ubuntu@<your-ec2-ip>:/tmp/
```

Then on the server:
```bash
sudo cp /tmp/service_account.json /opt/wantahero/credentials/service_account.json
sudo chown herobot:herobot /opt/wantahero/credentials/service_account.json
sudo chmod 600 /opt/wantahero/credentials/service_account.json
```

### Step 6 — Enable Sheets in .env

```bash
sudo nano /opt/wantahero/.env
```

Set:

```
GOOGLE_SHEETS_ENABLED=true
GOOGLE_CREDENTIALS_PATH=credentials/service_account.json
GOOGLE_SPREADSHEET_ID=your_spreadsheet_id_here
```

Then restart:
```bash
sudo systemctl restart wantahero
```

---

## File Structure

```
want-a-hero-bot/
├── bot.py               ← main bot, all slash commands
├── config.py            ← environment-driven configuration
├── database.py          ← SQLite CRUD layer
├── sheets.py            ← Google Sheets integration
├── alliances.py         ← alliance list manager (backed by data/alliances.json)
├── heroes.py            ← hero list manager (backed by data/heroes.json)
├── sanitize.py          ← input validation and sanitization
├── logger_setup.py      ← rotating log configuration
├── requirements.txt
├── .env.example         ← copy to .env and fill in
├── setup.sh             ← Ubuntu EC2 one-shot installer
├── systemd/
│   └── wantahero.service
├── data/                ← SQLite DB + JSON lists (auto-created)
│   ├── hero_requests.db
│   ├── alliances.json
│   └── heroes.json
├── logs/                ← rotating log files (auto-created)
└── credentials/         ← place your Google service account JSON here
```

---

## Updating the Bot

Upload changed files and run the setup script again — it uses `rsync` and preserves your `.env` and `data/` directory:

```powershell
# From PowerShell — upload the whole repo folder
scp -i "C:\path\to\your-key.pem" -r . ubuntu@<your-ec2-ip>:~/want-a-hero-bot/
```

Then on the server:
```bash
cd ~/want-a-hero-bot
./setup.sh
sudo systemctl restart wantahero
```

For a full clean reinstall (wipes the old install, preserves `.env`):
```bash
sudo systemctl stop wantahero
[ -f /opt/wantahero/.env ] && sudo cp /opt/wantahero/.env ~/wantahero.env.bak
sudo rm -rf /opt/wantahero
cd ~/want-a-hero-bot && ./setup.sh
sudo cp ~/wantahero.env.bak /opt/wantahero/.env
sudo chown herobot:herobot /opt/wantahero/.env
sudo systemctl start wantahero
```

---

## Viewing Logs

```bash
# Live log stream
sudo journalctl -u wantahero -f

# Last 100 lines
sudo journalctl -u wantahero -n 100

# Persistent log files
sudo tail -f /opt/wantahero/logs/wantahero.log
```

---

## Troubleshooting

**Slash commands showing old/wrong options in Discord**  
Run `/hero_sync` in Discord to force Discord to re-register all commands immediately. If the command itself isn't visible yet, fully quit Discord (right-click tray icon → Quit Discord) and reopen it to clear the client cache.

**Slash commands not appearing at all**  
Make sure `GUILD_ID` is set in `.env` — without it the bot syncs globally which can take up to an hour. With `GUILD_ID` set, commands appear instantly on restart. Run `/hero_sync` after any deploy to force a refresh.

**Alliance or hero dropdown is empty**  
The `data/alliances.json` and `data/heroes.json` files may not exist yet. Restart the bot — it creates them with defaults automatically. If that doesn't help, check folder permissions:
```bash
sudo chown -R herobot:herobot /opt/wantahero/data/
```

**Google Sheets not updating**  
Check that `GOOGLE_SHEETS_ENABLED=true` in `.env` and that the service account email has Editor access on the sheet. Check logs for `Google Sheets write failed` errors.

**Google Sheets `unknown headers` error**  
Your sheet tab has an old column header (e.g. `Universal Medals` instead of `Selected for MGE`). The bot handles both automatically — no action needed. To clean it up manually, rename column G in any existing tabs.

**Bot crashes on startup**  
Run `sudo journalctl -u wantahero -n 50` and check for errors. Most common causes: `DISCORD_TOKEN` not set, credentials file missing, or a Python import error from a missing file.

**Reinstalling the bot application in Discord**  
If you remove and re-add the bot to your server, run `/hero_sync` once after it rejoins to re-register all slash commands.
