# Football Payment Bot

A Telegram bot for managing weekly amateur football games, tracking attendance, and handling payment accountability.

## Features

- **Game Management**: Create and manage football games with location, date, cost, and player limits
- **Attendance Tracking**: Players can join/leave via inline buttons; admin can manually manage participants
- **Payment Flow**: Admin-triggered payment phase with per-player cost calculation
- **Payment Tracking**: States include `not_paid` → `pending_confirmation` → `paid`
- **Transparency**: Live-updating group messages showing payment status
- **Debt Tracking**: Cross-game balance persistence
- **Reminders**: Scheduled pre-game and payment nudges via APScheduler

## Architecture

```
Bot Interface (python-telegram-bot)
  ↕
Application Logic Layer (Pydantic commands + services)
  ↕
Persistence Layer (SQLAlchemy 2.0 async + SQLite/PostgreSQL)
```

### Key Components

| Component | Location | Responsibility |
|-----------|----------|--------------|
| Bot Handlers | `bot/handlers/` | Telegram routing, keyboards, messages |
| Core Services | `core/services/` | Game, Player, Payment, Debt, Notification |
| Domain Events | `core/events.py` | In-memory event bus for decoupled notifications |
| Payment FSM | `payment/fsm.py` | State transition logic (not_paid → pending → paid) |
| Database | `db/` | SQLAlchemy models, repositories, UnitOfWork |
| Scheduler | `notifications/scheduler.py` | APScheduler for reminders and nudges |

## Setup

### 1. Environment Variables

Create a `.env` file:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
DATABASE_URL=sqlite+aiosqlite:///./football.db
ADMIN_TELEGRAM_IDS=123456789,987654321
REMINDER_INTERVAL_HOURS=24
NUDGE_INTERVAL_HOURS=48
LOG_LEVEL=INFO
```

### 2. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run the Bot

```bash
python -m bot.main
```

## Usage

### Admin Commands (Group)

- `/newgame` — Create a new game (conversation-based)
- `/pay <game_uuid>` — Trigger payment phase
- `/close <game_uuid>` — Close game
- `/cancel <game_uuid>` — Cancel game
- `/status <game_uuid>` — Show payment summary

### Player Commands (Group)

- Tap ✅ Join / ❌ Decline on game announcement
- `/debt` — Check your balance

### Private Commands

- `/start` — Onboard and register
- `/mygames` — List upcoming games
- `/pay <game_uuid>` — Show payment prompt
- Send screenshot after tapping 📷 Upload Screenshot

## Data Model

- **users** — Telegram user profiles with chat IDs
- **games** — Game metadata, status, and cost
- **participants** — Junction table with payment status and amount due
- **payments** — Audit log of all payment actions
- **user_balances** — Cross-game cumulative debt tracking

## Testing

Run integration tests:

```bash
python run_tests.py
```

## Project Structure

```
.
├── bot/                    # Telegram bot interface
│   ├── handlers/           # Group, private, callback handlers
│   ├── keyboards.py        # Inline keyboard builders
│   ├── messages.py         # Message formatters
│   └── middleware.py       # User registration middleware
├── core/                   # Domain logic
│   ├── commands.py         # Pydantic command models
│   ├── events.py           # Domain event bus
│   ├── exceptions.py       # Domain exceptions
│   ├── results.py          # CommandResult wrapper
│   └── services/           # Game, Player, Payment, Debt, Notification
├── db/                     # Persistence layer
│   ├── models.py           # SQLAlchemy declarative models
│   ├── session.py          # Engine and session factory
│   ├── unit_of_work.py     # Transaction management
│   └── repositories/       # Repository pattern implementations
├── payment/                # Payment utilities
│   ├── calculator.py       # Cost-per-player calculator
│   ├── fsm.py              # Payment state machine
│   └── screenshot.py       # Screenshot handler
├── notifications/          # Reminders and live messages
│   ├── scheduler.py        # APScheduler jobs
│   ├── live_message.py     # Live-updating group summary
│   └── nudges.py           # Private/group nudges
├── tests/                  # Test suite
├── config.py               # Environment configuration
└── requirements.txt        # Python dependencies
```

## Design Decisions

1. **SQLite first** — Simple local deployment; schema compatible with PostgreSQL for scale
2. **In-memory EventBus** — Sufficient for single-instance bot; can swap for Redis later
3. **No OCR in MVP** — Screenshots are optional evidence; admin confirmation is source of truth
4. **Manual payment trigger** — Prevents accidental premature payment requests
5. **UnitOfWork pattern** — Atomic transactions with automatic rollback on failure

## License

MIT
