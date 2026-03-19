# WindrangerBOT v2 🏹

Production-ready Discord bot for automated matchmaking, inhouse leagues, and MMR tracking. Built with `discord.py`, backed by MongoDB, and fully containerized for easy deployment.

## 🔥 Core Features

* **Modular Architecture:** Clean separation of logic using Discord Cogs (`cogs/`).
* **Multi-tenancy:** Strict data isolation between multiple Discord guilds.
* **High Performance:** Fully asynchronous operations with optimized MongoDB indexing (sub-millisecond queries).
* **Containerized:** Zero-downtime deployment with Docker & Docker Compose.
* **Self-Maintaining:** Configured log rotation, memory limits, and automatic crash recovery.

## 🛠 Tech Stack

* **Language:** Python 3.11+
* **Framework:** `discord.py` v2
* **Database:** MongoDB 7.0
* **Infrastructure:** Docker, Docker Compose

## ⚙️ Quick Start (Deployment)

### 1. Clone the repository

git clone [https://github.com/azverin7/WindrangerBOT_v2.git](https://github.com/azverin7/WindrangerBOT_v2.git)
cd WindrangerBOT_v2

2. Environment Setup
Create a .env file in the root directory with your credentials:

# Discord Bot Token
DISCORD_TOKEN=your_bot_token_here

# MongoDB Connection (Internal Docker Network)
MONGO_URI=mongodb://mongo:27017
3. Build & Run
Deploy the database and the bot in detached mode:

Bash
docker compose up -d
To view live logs: docker logs -f windranger_bot

📂 Project Structure
Plaintext
├── cogs/              # Isolated bot modules (lobby, stats, history, etc.)
├── core/              # Bot initialization, config, and custom loggers
├── database/          # MongoDB connection handlers and queries
├── utils/             # Decorators, checks, and helper functions
├── main.py            # Application entry point
├── Dockerfile         # Python environment build instructions
└── docker-compose.yml # Multi-container orchestration
 Administration
!setup — Initializes the database structure and required channels for the current guild.
##  Commands Reference

The bot uses prefix commands (default: `!`) and interactive Discord UI components (Buttons, Embeds) for a seamless matchmaking experience.

###  Administration
* `!setup` — Initializes the database structure, creates required categories, and sets up matchmaking channels for the current guild.
* `!reset_season` — Archives all current player statistics and starts a new competitive season (Admin only).
* `!cancel [match_id]` — Forcefully cancels an ongoing match and reverts player statistics.
* `!viewmode 1-5` — 

###  Matchmaking & Lobbies
* `!c` (or `!create`) — Creates a new active lobby in the matchmaking channel.
* *Note: Joining, leaving, and team drafting are handled entirely via interactive Discord Buttons attached to the lobby embed.*

###  Player Statistics & History
* `!stats [@user]` — Displays the current MMR/PTS, win rate, and total matches played for the user.
* `!top` — Shows the server's global leaderboard (Top players sorted by PTS).
