# Futsal Payment Bot — System Design Document

**Version:** 1.0  
**Status:** Draft → Implementation  
**Tech Stack:** Python 3.11+, `python-telegram-bot` (async), SQLAlchemy 2.0 (async), SQLite (dev) → PostgreSQL (prod), Pydantic, APScheduler, pytest

---

## 1. System Architecture (Logical)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              TELEGRAM PLATFORM                              │
│  (Group Chat, Private Chat, Inline Keyboards, Callback Queries, Photos)     │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────────┐
│                        BOT INTERFACE LAYER                                │
│  python-telegram-bot (Asyncio)                                            │
│  • GroupChatHandler    • PrivateChatHandler    • CallbackRouter           │
│  • ConversationManager (FSM)   • OnboardingHandler                        │
│  • MessageFormatter    • KeyboardBuilder                                │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────────┐
│                       APPLICATION LOGIC LAYER                             │
│  Service Orchestrator + Domain Services                                   │
│  • GameService    • PlayerService    • PaymentService                   │
│  • NotificationService    • DebtService                                   │
└──────────────┬───────────────┬───────────────┬──────────────────────────────┘
               │               │               │
┌──────────────▼──┐ ┌─────────▼────────┐ ┌────▼─────────────────────────────┐
│  PAYMENT FSM    │ │  REMINDER ENGINE │ │  DEBT TRACKER                    │
│  (State Machine)│ │  (APScheduler)   │ │  (Cross-game balance)            │
└─────────────────┘ └──────────────────┘ └──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────────┐
│                        PERSISTENCE LAYER                                  │
│  SQLAlchemy 2.0 AsyncSession + SQLite (now) / PostgreSQL (later)        │
│  • Users    • Games    • Participants    • Payments                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Breakdown

### 2.1 Bot Interface Layer
**Owner:** Bot Interaction Designer
**Responsibility:** Translate Telegram events into internal commands and render outgoing messages.
**Deliverables:**
- `bot/main.py` — Bot initialization, dispatcher wiring.
- `bot/handlers/` — Group handlers, private handlers, callbacks.
- `bot/keyboards.py` — Inline keyboard builders.
- `bot/messages.py` — Message templates & formatters.
- `bot/middleware.py` — User registration middleware (auto-capture `chat_id`, `telegram_id`).

**Interface Contract:**
- **Inbound:** Telegram `Update` objects → mapped to `internal commands` (Pydantic models in `core/commands.py`).
- **Outbound:** Service layer returns `CommandResult` (success/failure, data, errors) → Bot layer renders with `MessageFormatter`.
- **No business logic here.** Only routing, parsing, rendering, and user onboarding.

### 2.2 Application Logic Layer
**Owner:** Backend Architect
**Responsibility:** Core domain services, orchestration, validation, idempotency.
**Deliverables:**
- `core/services/` — `GameService`, `PlayerService`, `PaymentService`, `NotificationService`, `DebtService`.
- `core/commands.py` — Pydantic models for all inbound commands (e.g., `CreateGameCmd`, `JoinGameCmd`).
- `core/results.py` — Standardized result models (`CommandResult[T]`).
- `core/exceptions.py` — Domain exceptions (`GameNotFound`, `AlreadyJoined`, `NotAuthorized`).

**Interface Contract:**
- Services expose async methods accepting commands and returning results.
- All DB transactions managed via `UnitOfWork` pattern (SQLAlchemy session lifecycle).
- Services emit `DomainEvent` objects (e.g., `PlayerJoined`, `PaymentConfirmed`) to an in-memory event bus for decoupled notification handling.

### 2.3 Persistence Layer
**Owner:** Database Engineer
**Responsibility:** Schema, ORM models, migrations, query optimization, concurrency safety.
**Deliverables:**
- `db/models.py` — SQLAlchemy declarative models (`User`, `Game`, `Participant`, `Payment`).
- `db/migrations/` — Alembic migration scripts.
- `db/unit_of_work.py` — `UnitOfWork` context manager wrapping async sessions.
- `db/repositories/` — Repository classes per aggregate (`UserRepository`, `GameRepository`, etc.).

**Interface Contract:**
- Repositories expose async CRUD and domain-specific queries.
- `UnitOfWork` commits atomically; rollback on exception.
- Optimistic concurrency via row-level locks (`SELECT ... FOR UPDATE`) on `participants` and `payments` during join/pay actions to prevent race conditions.

### 2.4 Payment Flow / FSM
**Owner:** Payment Flow Designer
**Responsibility:** State transitions, payment calculation, screenshot handling, admin confirmation, debt tracking.
**Deliverables:**
- `payment/fsm.py` — Payment state machine (`not_paid` → `pending_confirmation` → `paid` / `rejected`).
- `payment/calculator.py` — Cost per player calculation (total cost / participant count).
- `payment/screenshot.py` — Photo receipt handler (stores `file_id`, optional OCR placeholder).
- `debt/service.py` — Cross-game balance aggregation.

**Interface Contract:**
- `PaymentService` delegates state transitions to the FSM module.
- `PaymentConfirmed` event triggers `DebtService` update and `NotificationService.notify_group_payment_update()`.
- All state changes logged with timestamp and actor (`user_id` or `admin_id`).

### 2.5 Notification / Reminder Service
**Owner:** Payment Flow Designer (collaboration with Bot Interface)
**Responsibility:** Scheduled reminders, nudges, live updating group messages.
**Deliverables:**
- `notifications/scheduler.py` — APScheduler jobs for pre-game reminders and payment nudges.
- `notifications/live_message.py` — Manager for pinned/edited group summary message.
- `notifications/nudges.py` — Private DM reminders and optional public group mentions.

**Interface Contract:**
- Consumes `DomainEvent` from event bus.
- Uses Bot Interface's `MessageSender` adapter (injected) to post messages.
- Configurable intervals via `BotConfig`.

---

## 3. Data Model (High-Level)

### Entities

#### `users`
| Column | Type | Notes |
|--------|------|-------|
| id | PK int | Internal |
| telegram_id | bigint unique | Telegram user ID |
| chat_id | bigint | Private DM chat ID (may differ from telegram_id) |
| username | text | Display name |
| first_name | text | |
| last_name | text | |
| created_at | timestamp | |
| is_active | boolean | Soft-delete flag |

#### `games`
| Column | Type | Notes |
|--------|------|-------|
| id | PK int | Internal |
| game_uuid | uuid unique | Public Game ID (shown to users) |
| created_by | FK users.id | Admin |
| location | text | |
| scheduled_at | timestamp | |
| total_cost | decimal(10,2) | Mutually exclusive with cost_per_player |
| cost_per_player | decimal(10,2) | |
| max_players | int nullable | |
| status | enum | `announced`, `closed`, `cancelled`, `completed` |
| group_chat_id | bigint | Where the game was announced |
| announcement_message_id | bigint | Message ID of the group post (for live editing) |
| payment_message_id | bigint | Message ID of payment instructions (for live editing) |
| created_at | timestamp | |

#### `participants` (junction)
| Column | Type | Notes |
|--------|------|-------|
| id | PK int | |
| game_id | FK games.id | |
| user_id | FK users.id | |
| joined_at | timestamp | |
| payment_status | enum | `not_paid`, `pending_confirmation`, `paid` |
| amount_due | decimal(10,2) | Snapshot at calculation time |
| confirmed_by | FK users.id nullable | Admin who confirmed |
| confirmed_at | timestamp nullable | |
| screenshot_file_id | text nullable | Telegram file_id |
| is_manual_add | boolean | True if added by admin |

#### `payments` (audit log)
| Column | Type | Notes |
|--------|------|-------|
| id | PK int | |
| participant_id | FK participants.id | |
| action | enum | `initiated`, `confirmed`, `rejected` |
| actor_id | FK users.id | Who performed the action |
| amount | decimal(10,2) | |
| notes | text nullable | Admin rejection reason |
| created_at | timestamp | |

#### `user_balances` (cross-game debt)
| Column | Type | Notes |
|--------|------|-------|
| id | PK int | |
| user_id | FK users.id | |
| amount_owed | decimal(10,2) | Positive = user owes money |
| last_updated | timestamp | |

**Key Constraints:**
- Unique composite index on `(game_id, user_id)` in `participants`.
- Check constraint: `games.total_cost IS NOT NULL OR games.cost_per_player IS NOT NULL`.
- `participants.payment_status` managed exclusively through `PaymentService`.

---

## 4. API / Event Design

### 4.1 Internal Commands (Bot → Application Layer)
```python
class CreateGameCmd(BaseModel):
    admin_id: int
    location: str
    scheduled_at: datetime
    total_cost: Optional[Decimal]
    cost_per_player: Optional[Decimal]
    max_players: Optional[int]
    group_chat_id: int

class JoinGameCmd(BaseModel):
    game_uuid: str
    user_id: int
    chat_id: int

class TriggerPaymentCmd(BaseModel):
    game_uuid: str
    admin_id: int
    card_number: str

class ConfirmPaymentCmd(BaseModel):
    participant_id: int
    admin_id: int
    approved: bool
    reason: Optional[str]
```

### 4.2 Domain Events (Application Layer → Notification/Reminder)
```python
class DomainEvent(BaseModel):
    event_id: str
    occurred_at: datetime

class PlayerJoined(DomainEvent):
    game_uuid: str
    user_id: int
    participant_count: int

class PlayerLeft(DomainEvent):
    game_uuid: str
    user_id: int
    participant_count: int

class PaymentInitiated(DomainEvent):
    game_uuid: str
    user_id: int
    amount: Decimal

class PaymentConfirmed(DomainEvent):
    game_uuid: str
    user_id: int
    amount: Decimal

class GameClosed(DomainEvent):
    game_uuid: str
```

### 4.3 Event Bus
Simple async in-memory event bus (sufficient for single-instance bot; if we scale later, swap for Redis Pub/Sub):
```python
class EventBus:
    async def publish(self, event: DomainEvent): ...
    def subscribe(self, event_type: Type[T], handler: Callable[[T], Awaitable[None]]): ...
```

---

## 5. State Transitions

### Game Lifecycle
```
[Admin creates] → announced → [Admin triggers payment] → payment_open → [Admin closes] → completed / cancelled
```

### Participant Payment FSM
```
not_paid --(player clicks "I Paid")--> pending_confirmation --(admin confirms)--> paid
                                              |
                                              +--(admin rejects)--> not_paid
```
- Idempotency: If player clicks "I Paid" again while `pending_confirmation`, return success without side effects.
- If player clicks "I Paid" while `paid`, return success (no-op).

### Join/Leave Idempotency
- If user clicks ✅ Join and already in list → return success (no-op).
- If user clicks ❌ Decline and not in list → return success (no-op).
- Race condition on max_players: Use `SELECT ... FOR UPDATE` on `participants` count during join transaction; reject if full.

---

## 6. Execution Plan

### Phase 1: Foundation (0–1 day)
1. Create project structure, dependencies (`requirements.txt`), `config.py`.
2. Database Engineer: Schema + models + migrations + UnitOfWork.
3. Backend Architect: Domain exceptions, commands, results, base service class.

### Phase 2: Core Game Flow (1–2 days)
4. Bot Interaction Designer: Onboarding + Group announcement handler + inline keyboards.
5. Backend Architect: `GameService` (create, list, close) + `PlayerService` (join, leave, manual add/remove).
6. Database Engineer: Repository implementations + transaction tests.

### Phase 3: Payment & Transparency (2–3 days)
7. Payment Flow Designer: Payment FSM + calculator + screenshot handler.
8. Backend Architect: `PaymentService` + `DebtService`.
9. Bot Interaction Designer: DM payment flow + group payment instructions.
10. Payment Flow Designer + Bot Interaction Designer: Live updating group message.

### Phase 4: Notifications & Polish (3–4 days)
11. Payment Flow Designer: Reminder scheduler + nudge logic.
12. Bot Interaction Designer: Public mention formatting + admin commands.
13. QA/Test Engineer: pytest suite for all services and edge cases (concurrency, idempotency).

### Phase 5: Integration & Hardening (4–5 days)
14. Full end-to-end manual test in a real Telegram group (with test bot).
15. Review, add rate-limiting, logging, error handling.
16. Handoff package: README, deployment notes, `.env.example`.

---

## 7. Cross-Component Contracts

| From | To | Contract |
|------|----|----------|
| Bot Interface | Application Layer | `Command` Pydantic models in, `CommandResult` out. Never passes raw Telegram objects deeper. |
| Application Layer | Persistence Layer | `UnitOfWork` context manager. Repositories accept entity IDs, return domain entities. |
| Application Layer | Notification Service | `EventBus.publish(DomainEvent)`. Fire-and-forget; notifications are best-effort. |
| Notification Service | Bot Interface | `MessageSender` interface (adapter pattern) so Notification Service doesn't depend on `python-telegram-bot` directly. |
| Payment Service | Debt Service | `DebtService.record_payment()` called synchronously within same UoW transaction as confirmation. |

---

## 8. Key Decisions & Trade-offs

| Decision | Rationale |
|----------|-----------|
| SQLite first, PostgreSQL later | Simplifies local dev & small-group deployment. Schema is compatible. |
| In-memory EventBus | Bot is single-instance; avoids infrastructure overhead. |
| No OCR in MVP | Screenshots are optional evidence; admin confirmation is the source of truth. |
| Manual payment trigger only | Prevents accidental premature payment requests; gives admin control. |
| `game_uuid` shown to users | Human-friendly reference without exposing internal DB IDs. |
| Pinned live message | Edits one message instead of spamming the group. |
| Debt tracking (cumulative) | Provides social pressure and long-term accountability. |

---

## 9. File Structure

```
/
├── DESIGN.md               # This document
├── README.md               # Human-facing quick start
├── .env.example            # Required env vars
├── requirements.txt
├── alembic.ini             # Migration config
├── bot/
│   ├── main.py
│   ├── config.py
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── group.py        # Group chat commands & callbacks
│   │   ├── private.py      # DM commands & onboarding
│   │   └── callbacks.py    # Inline button router
│   ├── keyboards.py
│   ├── messages.py
│   └── middleware.py
├── core/
│   ├── __init__.py
│   ├── commands.py
│   ├── results.py
│   ├── exceptions.py
│   ├── events.py
│   └── services/
│       ├── __init__.py
│       ├── game.py
│       ├── player.py
│       ├── payment.py
│       ├── notification.py
│       └── debt.py
├── payment/
│   ├── __init__.py
│   ├── fsm.py
│   ├── calculator.py
│   └── screenshot.py
├── notifications/
│   ├── __init__.py
│   ├── scheduler.py
│   ├── live_message.py
│   └── nudges.py
├── db/
│   ├── __init__.py
│   ├── models.py
│   ├── session.py
│   ├── unit_of_work.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── game.py
│   │   └── participant.py
│   └── migrations/
├── tests/
│   ├── conftest.py
│   ├── test_game_service.py
│   ├── test_payment_flow.py
│   └── test_idempotency.py
└── scripts/
    └── run_bot.py
```

---

## 10. Environment Variables (.env.example)

```bash
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=sqlite+aiosqlite:///./football.db
GROUP_CHAT_ID=          # Optional default group
REMINDER_INTERVAL_HOURS=24
NUDGE_INTERVAL_HOURS=48
ADMIN_TELEGRAM_IDS=123456789,987654321
LOG_LEVEL=INFO
```
