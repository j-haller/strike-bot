# Strike Bot

A Discord bot for managing strikes against server members using a democratic poll system.

## How it works

When a strike is proposed against a member, a poll is created in the channel. Registered members can vote Yes or No. Once a majority vote is reached, the poll closes early and the strike is either accepted or rejected. Polls last up to 1 hour.

## Commands

| Command | Description |
|---|---|
| `/addmember <member>` | Register a server member so they can vote and receive strikes |
| `/addstrike <member> [strikes]` | Start a poll to give a member strikes (default: 1, max: 5) |
| `/showstrikes [member]` | Show accepted strikes for a member, or all members if none specified |
| `/help` | Show available commands |

> **Note:** `!sync` is a prefix command (not a slash command) that syncs slash commands to the current guild.

## Setup

### Prerequisites

- Python 3.12+
- A Discord bot token with the following intents enabled:
  - Message Content
  - Server Members
  - Polls

### Configuration

Copy `.env.example` to `.env` and fill in the values:

```env
DISCORD_TOKEN=your_discord_bot_token
DB_PATH=data/db.sqlite
DB_SCHEMA_PATH=db/schema.sql
```

### Run locally

```bash
pip install -r requirements.txt
python -m bot.main
```

### Run with Docker

**Development** (with hot reload):
```bash
docker compose --profile dev up
```

**Production**:
```bash
docker compose --profile prod up -d
```

## Database

SQLite is used for persistence. The schema is initialized automatically on startup from `db/schema.sql`.

Two tables are used:
- `user` — registered guild members
- `strike` — strike records with status (`pending`, `accepted`, `rejected`)
