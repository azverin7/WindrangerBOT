
# WindrangerBOT 🏹

[🇷🇺 Читать на русском (Russian Version)](#русская-версия-russian-version)

**WindrangerBOT** is a stateless, highly scalable, and fully automated Discord inhouse matchmaking system. Designed with HighLoad architecture principles, it replaces legacy, prefix-based, and state-heavy bots by offering seamless concurrent lobby management, strict Role-Based Access Control (RBAC), and Ephemeral UX isolation.

## 🚀 Key Features

* **Stateless Architecture:** No limits on concurrent lobbies. Multiple hosts can run parallel matchmaking sessions in the same channel without blocking the Event Loop or overlapping states. Single Source of Truth is MongoDB.
* **Self-Healing Infrastructure:** Uses Lazy Initialization. If a server admin accidentally deletes a bot-created category, role, or channel, the bot will dynamically recreate the missing infrastructure and update database pointers on the next command execution.
* **UX Isolation & Command Routing:** Zero chat spam. Heavy queries (match history, personal stats) are routed through Ephemeral (`ephemeral=True`) messages. Commands are strictly locked to their respective channels (e.g., `/stats` only works in the `#stats` channel).
* **3-Tier RBAC Model:** Strict hierarchy for server management:
    * **Level 0 (Owner/Dev):** Full database wipes (`/hard_reset`).
    * **Level 1 (Grand Host):** Infrastructure setup (`/setup`), staff management (`/add_host`, `/remove_host`).
    * **Level 2 (Host):** Matchmaking control, player punishment (`/punish`), and PTS mutation.
* **Automated Tribunal (Garbage Collector):** Asynchronous background worker (`tasks.loop`) handles ban expirations, automatically removes penalty roles, and transactionally redraws the Hall of Shame leaderboard without manual admin intervention.
* **Smart Auto-Balancer:** Distributes players into two teams (Radiant/Dire) based on their PTS/MMR using a Snake Draft algorithm, automatically creates temporary Voice Channels, and moves players.

## 🛠️ Tech Stack

* **Python 3.10+**
* **discord.py** (Slash commands, UI Views, Context Menus)
* **MongoDB** (Motor async driver)
* **Docker & Docker Compose**

## ⚙️ Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/yourusername/windranger-bot.git](https://github.com/yourusername/windranger-bot.git)
   cd windranger-bot
Configure Environment Variables:
Create a .env file in the root directory:

Code fragment
BOT_TOKEN=your_discord_bot_token_here
MONGO_URI=mongodb://mongo:27017/windranger
DEVELOPER_ID=your_discord_user_id
Deploy with Docker Compose:

Bash
docker compose up -d --build
Initialize Server Infrastructure:
Once the bot is invited to your Discord server, the Server Owner or Developer must run:

Plaintext
/setup
This will generate the necessary categories, text channels, voice waiting rooms, and roles (Grand Host, Host, Close Ban).

📜 Commands Reference
/setup — Initialize or repair server infrastructure (Admin/Dev).

/lobby — Create a new 5v5 matchmaking lobby (Host+).

/fill — Fill the current lobby with dummy bots for testing (Host+).

/punish — Ban a player from matchmaking and deduct PTS (Host+).

/unban — Manually remove a ban and penalty role (Host+).

/set_pts — Manually mutate a player's PTS (Host+).

/add_host / /remove_host — Manage staff roles (Grand Host+).

/refresh_lb — Force redraw the leaderboard embed (Host+).

/history — View the last matches played on the server (Public).

/stats — View personal or target player's seasonal statistics (Public).

<a name="русская-версия-russian-version"></a>

# WindrangerBOT 🏹 (Русская версия)
WindrangerBOT — это stateless, масштабируемая и полностью автоматизированная inhouse-матчмейкинг система для Discord. Спроектирована по стандартам HighLoad для замены устаревших ботов на префиксах. Обеспечивает параллельное управление любым количеством лобби, строгую ролевую модель (RBAC) и изоляцию пользовательского опыта (Ephemeral UX).

# # 🚀 Основные возможности
Stateless Архитектура: Отсутствие лимитов на количество одновременных лобби. Разные хосты могут собирать матчи параллельно в одном канале без блокировки Event Loop'а. Вся логика опирается на MongoDB (Single Source of Truth).

Self-Healing Инфраструктура (Самовосстановление): Паттерн ленивой инициализации. Если администратор случайно удалит категорию, роль или канал бота, при следующем вызове команды бот динамически воссоздаст утерянные сущности и обновит связи в БД.

UX-Изоляция и Маршрутизация: Никакого спама в чатах. Тяжелые запросы (история, статистика) отдаются через эфемерные сообщения (ephemeral=True). Команды жестко привязаны к целевым каналам (например, /stats работает только в канале #статистика).

Трехуровневая RBAC-модель: Строгая иерархия доступов:

Уровень 0 (Owner/Dev): Полный вайп БД (/hard_reset).

Уровень 1 (Grand Host): Развертывание инфры (/setup), управление персоналом (/add_host, /remove_host).

Уровень 2 (Host): Управление лобби, наказания (/punish), ручная выдача PTS.

Автоматизированный Трибунал (Garbage Collector): Асинхронный фоновый воркер (tasks.loop) сам отслеживает истекшие баны, снимает штрафные роли и транзакционно перерисовывает лидерборд нарушителей без участия админов.

Умный Автобалансер: Распределяет игроков на две команды (Свет/Тьма) на основе их PTS/MMR с помощью алгоритма змейки (Snake Draft), автоматически создает временные голосовые каналы и мутит автоматический мув игроков.

# # 🛠️ Стек технологий
Python 3.10+

discord.py (Слэш-команды, UI Views, Context Menus)

MongoDB (Асинхронный драйвер Motor)

Docker & Docker Compose

# # ⚙️ Установка и Запуск
Клонируйте репозиторий:

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/yourusername/windranger-bot.git](https://github.com/yourusername/windranger-bot.git)
   cd windranger-bot
Настройте переменные окружения:
Создайте файл .env в корневой директории:

Фрагмент кода
BOT_TOKEN=ваш_токен_дискорд_бота
MONGO_URI=mongodb://mongo:27017/windranger
DEVELOPER_ID=ваш_discord_user_id
Запустите через Docker Compose:

Bash
docker compose up -d --build
Инициализация инфраструктуры сервера:
После добавления бота на сервер, Владелец сервера или Разработчик должен выполнить:

Plaintext
/setup
Эта команда сгенерирует необходимые категории, текстовые каналы, голосовую комнату ожидания и роли (Grand Host, Host, Close Ban).

# # 📜 Справочник команд
/setup — Создать или восстановить инфраструктуру сервера (Admin/Dev).

/lobby — Создать новое 5v5 лобби (Host+).

/fill — Заполнить текущее лобби ботами для тестирования (Host+).

/punish — Заблокировать игрока и вычесть PTS (Host+).

/unban — Вручную снять блокировку и штрафную роль (Host+).

/set_pts — Вручную установить PTS игроку (Host+).

/add_host / /remove_host — Управление ролями хостов (Grand Host+).

/refresh_lb — Принудительно перерисовать лидерборд (Host+).

/history — Посмотреть последние матчи сервера (Public).

/stats — Посмотреть статистику за текущий сезон (Public).
