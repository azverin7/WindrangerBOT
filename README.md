# WindrangerBOT 🏹

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)](https://python.org)
[![Discord.py](https://img.shields.io/badge/Discord.py-2.3-blue?logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![MongoDB](https://img.shields.io/badge/MongoDB-7.0-green?logo=mongodb&logoColor=white)](https://www.mongodb.com)
[![Docker](https://img.shields.io/badge/Docker-Enabled-blue?logo=docker&logoColor=white)](https://www.docker.com)

**WindrangerBOT** is a stateless, highly scalable, and fully automated Discord in-house matchmaking system. Designed with High-Load architectural principles, it replaces legacy, state-heavy prefix bots by offering concurrent lobby management, strict Role-Based Access Control (RBAC), and optimized Ephemeral UX isolation.

---

## 🚀 Key Features

*   **Stateless Concurrency Architecture:** No limits on simultaneous matchmaking. Multiple hosts can run parallel sessions in the exact same channel without event-loop blocking or state collisions. MongoDB serves as the Single Source of Truth (SSOT).
*   **Self-Healing Infrastructure Pattern:** Leverages lazy initialization. If an administrator accidentally deletes a bot-created category, role, or channel, the system dynamically reconstructs the missing resources and updates database pointers during the next command execution.
*   **Strict Ephemeral UX Isolation:** Zero chat pollution. Heavy queries, personal performance metrics, and match histories are delivered exclusively via ephemeral messages (`ephemeral=True`). Interactive commands are strictly bound to their designated channels.
*   **3-Tier Role-Based Access Control (RBAC):** Rigid permission hierarchy:
    *   **Level 0 (Owner/Dev):** Complete database truncation (`/hard_reset`).
    *   **Level 1 (Grand Host):** System setup (`/setup`), staff orchestration (`/add_host`, `/remove_host`).
    *   **Level 2 (Host):** Matchmaking life-cycle management, penalty assignments (`/punish`), and PTS adjustments.
*   **Asynchronous Lifecycle Garbage Collector:** A dedicated background task (`tasks.loop`) continuously monitors penalty expirations, removes restrictions, and transactionally updates leaderboards without human intervention.
*   **Algorithmic Snake Draft Balancer:** Distributes matched players into balanced teams based on their current PTS rating, automatically provisions isolated temporary voice rooms, and executes atomic, multi-threaded player relocation.

---

## 🛠️ Technical Specification

*   **Runtime:** Python 3.11 (optimized with native `asyncio` loops)
*   **Framework:** `discord.py` v2+ (using Slash Commands, Interactive Views, UI Modals, and Context Menus)
*   **Database:** MongoDB via `motor` (fully asynchronous Driver)
*   **Deployment:** Docker & Docker Compose multi-container setup

---

## ⚙️ Deployment & Initialization

### 1. Clone the repository
```bash
git clone https://github.com/azverin7/WindrangerBOT.git
cd WindrangerBOT
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory:
```env
BOT_TOKEN=your_discord_bot_token_here
MONGO_URI=mongodb://mongo:27017/windranger
DEVELOPER_ID=your_discord_user_id
```

### 3. Build and Spin Up Containers
```bash
docker compose up -d --build
```

### 4. Provision Discord Server
Once the bot joins your server, the Developer or Server Owner must execute the initialization command in any channel:
```plaintext
/setup
```
This triggers the self-healing engine to dynamically construct categories, waiting lounges, match voice channels, and setup administrative roles (`Grand Host`, `Host`, `Close Ban`).

---

## 📜 Unified Commands Registry

*   `/setup` — Provision, repair, or restore missing server infrastructure (Admin/Dev).
*   `/lobby` — Spawn a new 5v5 matchmaking lobby instance (Host+).
*   `/fill` — Instantly populate the active lobby with synthetic bots for stress-testing (Host+).
*   `/punish` — Execute player ban, assign penalty roles, and deduct PTS (Host+).
*   `/unban` — Lift a matchmaking ban and strip penalty roles prematurely (Host+).
*   `/set_pts` — Manually mutate a player's seasonal PTS value (Host+).
*   `/add_host` / `/remove_host` — Manage administrative access and staff delegation (Grand Host+).
*   `/refresh_lb` — Force a transactional redraw of the public leaderboards (Host+).
*   `/history` — Retrieve historical match data from the server database (Public).
*   `/stats` — Query personal or target player's metrics for the current season (Public).

---

<a name="русская-версия-russian-version"></a>

# WindrangerBOT 🏹 (Русская версия)

**WindrangerBOT** — это stateless, высокопроизводительная и полностью автоматизированная in-house матчмейкинг система для Discord. Архитектура спроектирована по стандартам отказоустойчивых систем с высокой нагрузкой для полной замены устаревших ботов на префиксах. Обеспечивает параллельное проведение матчей без лимитов, строгую ролевую модель (RBAC) и изоляцию пользовательского интерфейса (Ephemeral UX).

---

## 🚀 Ключевые Преимущества

*   **Stateless-Архитектура Конкурентности:** Отсутствие ограничений на количество одновременных матчей. Несколько хостов могут собирать лобби в одном канале без риска коллизий состояний или блокировки Event Loop. Единым источником правды (SSOT) выступает MongoDB.
*   **Паттерн Самовосстановления (Self-Healing):** Ленивая инициализация ресурсов. Если администратор случайно удалит категорию, голосовой канал или служебную роль, бот автоматически восстановит всю структуру базы данных и Discord-сервера при следующем вызове любой команды.
*   **Строгая Изоляция Пользовательского Опыта:** Отсутствие спама в публичных текстовых каналах. Все тяжелые запросы (личная статистика, история игр) отправляются исключительно в виде эфемерных сообщений (`ephemeral=True`). Команды жёстко привязаны к соответствующим текстовым каналам.
*   **Трёхъярусная Ролевая Модель (RBAC):** Чёткая иерархия уровней доступа для персонала:
    *   **Уровень 0 (Владелец/Разработчик):** Полная очистка базы данных и сброс настроек (`/hard_reset`).
    *   **Уровень 1 (Grand Host):** Инициализация инфраструктуры (`/setup`), назначение персонала (`/add_host`, `/remove_host`).
    *   **Уровень 2 (Host):** Управление жизненным циклом лобби, вынесение приговоров нарушителям (`/punish`) и ручной контроль PTS.
*   **Асинхронный Сборщик Мусора (Tribunal GC):** Фоновый процесс (`tasks.loop`) непрерывно отслеживает активные блокировки в базе данных, автоматически снимает штрафные роли и транзакционно обновляет таблицы лидеров без участия администрации.
*   **Балансировщик на Алгоритме Змейки:** Распределяет десять участников на две сбалансированные команды на основе их текущего рейтинга (PTS), создаёт временные изолированные голосовые комнаты и осуществляет быстрый атомарный перенос игроков.

---

## 🛠️ Технический Стек

*   **Среда выполнения:** Python 3.11 (с оптимизацией под асинхронные вызовы)
*   **Библиотека:** `discord.py` v2+ (задействованы Slash-команды, интерактивные представления, модальные окна и контекстные меню)
*   **База данных:** MongoDB через асинхронный драйвер `motor`
*   **Контейнеризация:** Мультиконтейнерная архитектура Docker & Docker Compose

---

## ⚙️ Установка и Запуск

### 1. Клонирование репозитория
```bash
git clone https://github.com/azverin7/WindrangerBOT.git
cd WindrangerBOT
```

### 2. Настройка переменных окружения
Создайте файл `.env` в корневой директории проекта:
```env
BOT_TOKEN=ваш_токен_дискорд_бота
MONGO_URI=mongodb://mongo:27017/windranger
DEVELOPER_ID=ваш_discord_user_id
```

### 3. Сборка и запуск контейнеров
```bash
docker compose up -d --build
```

### 4. Инициализация инфраструктуры сервера
После добавления бота на ваш Discord-сервер, Разработчик или Владелец сервера должен выполнить следующую команду в любом канале:
```plaintext
/setup
```
Бот автоматически развернет категорию, текстовые каналы статистики и лобби, голосовые комнаты ожидания, а также создаст необходимые роли управления (`Grand Host`, `Host`, `Close Ban`).

---

## 📜 Сводный Реестр Команд

*   `/setup` — Создать, проверить или восстановить повреждённую инфраструктуру сервера (Администратор/Разработчик).
*   `/lobby` — Инициировать создание нового лобби формата 5х5 (Хост+).
*   `/fill` — Моментально заполнить текущее лобби синтетическими ботами для тестирования (Хост+).
*   `/punish` — Заблокировать игрока на сервере, выдать штрафную роль и списать PTS (Хост+).
*   `/unban` — Досрочно снять блокировку матчмейкинга и удалить штрафную роль (Хост+).
*   `/set_pts` — Вручную перезаписать сезонное количество PTS у игрока (Хост+).
*   `/add_host` / `/remove_host` — Делегирование прав управления персоналу сервера (Grand Host+).
*   `/refresh_lb` — Принудительно инициировать транзакционную перерисовку лидерборда (Хост+).
*   `/history` — Запросить историю последних сыгранных матчей на сервере (Все пользователи).
*   `/stats` — Выгрузить подробную статистику игрока за текущий сезон (Все пользователи).
