# Want-A-Hero Bot

A Discord bot for tracking Age of Empires Mobile hero-unlock medal requests.  
Runs on Ubuntu EC2, stores data in SQLite, and optionally syncs to Google Sheets (one tab per MGE week, Monday–Sunday UTC).

---

## Commands

| Command | Who can use | Description |
|---|---|---|
| `/wantahero` | Everyone | Submit a hero request |
| `/hero_report [week_offset]` | Hero Admin | List requests (0 = current week, -1 = last week) |
| `/hero_delete request_id` | Hero Admin | Delete one request by ID |
| `/hero_update request_id [fields]` | Hero Admin | Edit any field on a request |
| `/hero_clear confirm:YES` | Hero Admin | Wipe **all** requests |

Admin access is granted to anyone with the **Hero Admin** Discord role (or Server Administrator permission).  
The role name can be changed via the `ADMIN_ROLE_NAME` environment variable.

---

## Quick-Start (Ubuntu EC2)

### 1 — Launch an EC2 instance

- **AMI**: Ubuntu 22.04 LTS (or 24.04)  
- **Instance type**: t3.micro is plenty  
- **Security group**: outbound HTTPS (443) required; no inbound ports needed for the bot  
- **Key pair**: keep your `.pem` safe  

### 2 — SSH in and clone the repo

```bash
ssh -i your-key.pem ubuntu@<your-ec2-ip>
git clone https://github.com/your-org/want-a-hero-bot.git
cd want-a-hero-bot
```

### 3 — Run the setup script

```bash
chmod +x setup.sh
./setup.sh
```

This installs Python, creates a dedicated `herobot` user, sets up `/opt/wantahero`, installs the venv, and registers the systemd service.

### 4 — Create your Discord bot

1. Go to <https://discord.com/developers/applications> → **New Application**
2. Name it (e.g. *Want-A-Hero*)
3. **Bot** tab → **Add Bot** → copy the **Token**
4. **OAuth2 → URL Generator**: select scopes `bot` + `applications.commands`; permissions: `Send Messages`, `Embed Links`, `Use Slash Commands`
5. Open the generated URL in your browser and invite the bot to your server
6. In your server, create a role named exactly **`Hero Admin`** and assign it to your officers/admins

### 5 — Configure environment variables

```bash
sudo nano /opt/wantahero/.env
```

Fill in at minimum:

```
DISCORD_TOKEN=your_discord_bot_token_here
ADMIN_ROLE_NAME=Hero Admin
```

### 6 — Start the bot

```bash
sudo systemctl start wantahero
sudo systemctl status wantahero        # should show "active (running)"
sudo journalctl -u wantahero -f        # live logs
```

The service is set to restart automatically on failure and on EC2 reboot.

---

## Google Sheets Setup (Optional)

Each time someone submits a `/wantahero` request the bot appends a row to your spreadsheet.  
Tabs are named `Week YYYY-MM-DD` (the Monday of that MGE week).

### Step 1 — Create a Google Cloud project

1. Go to <https://console.cloud.google.com/> → **New Project** (name it e.g. *WantAHeroBot*)
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

1. Create a new Google Sheet (or use an existing one)
2. Copy the **spreadsheet ID** from the URL:  
   `https://docs.google.com/spreadsheets/d/**THIS_PART**/edit`
3. Click **Share** and add the service account email (looks like `wantahero-bot@your-project.iam.gserviceaccount.com`) as an **Editor**

### Step 5 — Upload credentials to EC2

```bash
scp -i your-key.pem service_account.json ubuntu@<your-ec2-ip>:~/
ssh -i your-key.pem ubuntu@<your-ec2-ip>
sudo cp service_account.json /opt/wantahero/credentials/
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

Then restart: `sudo systemctl restart wantahero`

---

## Google Sheets — Manual / Walk-In Requests

Players who don't have Discord access can add their own row directly in the sheet.  
Use the following column order (the bot will skip rows it didn't write):

| Column | Value |
|---|---|
| A — Request ID | Leave blank (or write `MANUAL`) |
| B — Discord User | Their Discord tag if known, or their name |
| C — Game Name | In-game name (required) |
| D — Alliance | Alliance name (required) |
| E — Medals Needed | Number (required) |
| F — Universal Medals | Number or leave blank |
| G — Submitted At (UTC) | Leave blank or fill in date/time |

---

## File Structure

```
want-a-hero-bot/
├── bot.py               ← main bot entry point
├── config.py            ← environment-driven configuration
├── database.py          ← SQLite CRUD layer
├── sheets.py            ← Google Sheets integration
├── logger_setup.py      ← rotating log configuration
├── requirements.txt
├── .env.example         ← copy to .env and fill in
├── setup.sh             ← Ubuntu EC2 installer
├── systemd/
│   └── wantahero.service
├── data/                ← SQLite DB lives here (auto-created)
├── logs/                ← rotating log files (auto-created)
└── credentials/         ← Google service account JSON (you add this)
```

---

## Updating the Bot

```bash
cd ~/want-a-hero-bot
git pull
sudo rsync -av --exclude='.git' --exclude='.env' --exclude='__pycache__' \
    --exclude='*.pyc' --exclude='.venv' ./ /opt/wantahero/
sudo -u herobot /opt/wantahero/.venv/bin/pip install -r /opt/wantahero/requirements.txt
sudo systemctl restart wantahero
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

**Bot isn't responding to `/wantahero`**  
Run `sudo journalctl -u wantahero -n 50` and look for errors. The most common causes are an invalid token or the bot not having `applications.commands` scope.

**Slash commands not appearing in Discord**  
It can take up to an hour for global slash commands to propagate. If you're in a hurry you can register them to a single guild (server) instead — see the discord.py docs for `guild=discord.Object(id=YOUR_SERVER_ID)`.

**Google Sheets not updating**  
Check that `GOOGLE_SHEETS_ENABLED=true` in `.env` and that the service account email has been shared as Editor on the sheet. Check logs for `Google Sheets write failed` errors.

**Bot crashes on startup**  
Make sure `DISCORD_TOKEN` is set correctly in `/opt/wantahero/.env`.
