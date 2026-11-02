# Reminder Agent

A personal "inbox" agent I built to learn AI engineering hands-on. I send it messy text through Telegram ("dsa quiz wednesday 2pm", or a pasted official notice). An LLM turns the text into structured data, SQLite stores it, and a loop sends me reminders and a morning briefing on Telegram.

Everything here uses free tools: Python, Telegram Bot API, Gemini API free tier, SQLite. No server is rented. It runs on my MacBook while a terminal is open.

Started: 2026-10-24. Last updated: 2026-11-02.

---

## Where I left off 

- Everything in "What it can do" works and is in daily use.
- The 5 manual delete-confirmation tests were skipped (see Status). The plan is to replace them with automated tests.
- Next up, in order: automated tests, `requirements.txt` + `.env.example`, chat memory that survives restarts, logging to a file, then a feature from "Ideas for next time".
- Before starting the bot: `pgrep -fl bot.py` should print nothing. Two copies of the bot fight over one Telegram token (see "Things that went wrong").

## What it can do

- Understand free-form messages and save them as events (title, date/time, location, notes).
- Understand relative dates ("thursday", "tomorrow", "today evening") because the current date and timezone are put into every prompt.
- Refuse to guess: if the date or time is missing it asks instead of saving.
- Schedule reminders for each event: 1 day before, 2 hours before, 30 minutes before, and at the event time. Reminders already in the past are skipped, and the bot says so when none could be scheduled.
- Act like a real agent: the model chooses between tools (add, list, cancel, reschedule, list reminders) and can chain them ("move the dsa quiz to thursday" looks up the id first, then reschedules).
- Ask for confirmation before deleting anything. The confirmation is enforced in code, not in the prompt.
- Detect exact duplicates (same title ignoring case, same time) and refuse to add them twice.
- Send a daily briefing (today and tomorrow) between 08:00 and 20:59 once per day. If the laptop wakes up late, the briefing still goes out that day. `/today` shows it on demand.
- Survive network trouble: failed Telegram calls are logged and retried instead of crashing the bot, and a reminder is only marked as sent if the message actually went out.
- Plain commands that skip the AI: `/list`, `/today`, `/cancel <id>`.

## How it works

```
Telegram message
      |
      v
bot.py (loop: poll Telegram every ~5s, then check reminders and briefing)
      |
      |-- /list, /today, /cancel <id>  -> plain code, no AI
      |-- "yes"/"no" while a deletion is pending -> plain code, no AI
      |
      v
agent.py  handle_message()
      |  sends message + recent chat + tool menu + rules to Gemini
      |  Gemini either answers in text, or asks for a tool call
      |  we run the tool (db.py), send the result back, repeat (max 6 steps)
      v
db.py (SQLite: agent.db)
      ^
      |-- due_reminders() checked every loop by bot.py -> send -> mark_sent only on success
      |-- briefing.py builds the daily briefing from the events table
```

The four parts of every agent, as they appear here:

| Part | In this project |
|---|---|
| Trigger | The polling loop in `bot.py` (new message, a reminder coming due, or the morning briefing window) |
| Brain | Gemini, called from `agent.py` (a cloud model, not a local one) |
| Tools | Python functions in `db.py`, exposed to the model by `agent.py` |
| Memory | SQLite (`agent.db`) for events, reminders and small state; last 12 chat turns in RAM for context |

## Files

| File | What it is |
|---|---|
| `bot.py` | Main program. Run this. Telegram polling loop, commands, reminder and briefing sending, single-instance lock, network error handling. |
| `agent.py` | The agent: tool declarations, system prompt, the tool-calling loop, duplicate check, confirm-before-delete, retry on 503/429. Can be tested alone with `python agent.py`. |
| `db.py` | SQLite tables and all database functions (events, reminders, key-value state). |
| `briefing.py` | Builds the daily briefing text and decides whether one is due. No AI involved. |
| `extract.py` | The earlier version: one-shot "message to JSON" extraction. No longer used by the bot, kept for comparison. |
| `get_chat_id.py` | One-time helper that prints my Telegram chat ID. |
| `hello.py` | First test: sends one message from code. |
| `list_models.py` | Prints the Gemini model names my key can use. |
| `ask.py` | First test: one plain LLM call. |
| `.env` | Secrets. **Never commit.** (Ignored by git.) |
| `agent.db` | The database, created automatically. Ignored by git. |
| `bot.lock` | Created while the bot runs, to stop a second copy from starting. Ignored by git. |

## Setup from scratch (new machine or fresh clone)

1. Install Python 3.10+. On macOS the command is `python3`, not `python` (until a venv is active).
2. In the project folder:
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install requests google-genai python-dotenv
   ```
   The venv gives this project its own private set of libraries. `source .venv/bin/activate` switches the terminal into it (look for `(.venv)` in the prompt).
3. Create the Telegram bot: message @BotFather, `/newbot`, copy the token. Then send any message to the new bot.
4. Get a free Gemini key at aistudio.google.com/app/apikey.
5. Create `.env` (no quotes, no spaces around `=`):
   ```
   TELEGRAM_TOKEN=...
   TELEGRAM_CHAT_ID=...
   GEMINI_API_KEY=...
   ```
   Get the chat ID by running `python get_chat_id.py` after messaging the bot.
6. Make sure `.gitignore` contains: `.env`, `.venv/`, `agent.db`, `__pycache__/`, `bot.lock`.

## Running it

```
cd reminder-agent
source .venv/bin/activate
pgrep -fl bot.py          # should print nothing; if it prints a line, a copy is already running
caffeinate -i python bot.py
```

`caffeinate -i` stops the Mac from idle-sleeping while the bot runs (closing the lid still sleeps it). Stop the bot with Ctrl+C. Reminders only fire while it is running.

To test the agent without Telegram: `python agent.py` (type messages at the `you>` prompt, tool calls are printed).

To check for syntax or indentation errors without running: `python -m py_compile db.py agent.py bot.py briefing.py`.

To look inside the database:
```
sqlite3 agent.db "SELECT * FROM events;"
sqlite3 agent.db "SELECT id, event_id, remind_at, sent FROM reminders;"
sqlite3 agent.db "SELECT * FROM state;"
```

To make the briefing fire again for testing: `sqlite3 agent.db "DELETE FROM state;"` and restart the bot.

## Config values worth knowing

- Model: `MODEL = "gemini-2.5-flash"` in `agent.py` (and `extract.py`). Model names change often, so run `python list_models.py` to see what is available. Avoid `preview`, `tts`, `image`, `audio`, `live` models; be careful with `-latest` aliases because they silently change. If you hit rate limits, try `gemini-2.5-flash-lite`.
- Timezone: `Asia/Dhaka`, set in `agent.py`, `extract.py`, `db.py`. All times are stored as local `YYYY-MM-DDTHH:MM` text, which sorts correctly as plain text.
- Reminder offsets: the `OFFSETS` list at the top of `db.py`.
- Polling: `timeout: 5` in `get_updates` in `bot.py`. This is why reminders arrive within a few seconds of their time.
- Day parts: morning 09:00, afternoon 14:00, evening 18:00, night 21:00 (defined in the system prompt in `agent.py`).
- Briefing window: `first_hour=8`, `last_hour=20` in `briefing_due()` in `briefing.py`.

## Database

Three tables in `agent.db`:

- `events(id, title, when_at, location, notes)` (the column is `when_at` because `WHEN` is an SQL keyword).
- `reminders(id, event_id, remind_at, text, sent)`: one row per reminder, so the scheduler is just "find rows where `remind_at` has passed and `sent = 0`, send, mark sent".
- `state(key, value)`: tiny key-value store. Currently holds `last_briefing` (the date the last briefing was sent), so restarting the bot never sends a second one the same day.

`due_reminders()` only returns reminders whose event has not started yet, except the "now" reminder, which may fire up to 10 minutes late. So if the bot was off for a day it will not send stale "in 30 minutes" messages for past events.

Always insert with `?` placeholders, never by pasting text into SQL strings.

## Design decisions (and why)

- **Telegram, not WhatsApp/Discord.** WhatsApp's API needs a business account; unofficial libraries risk a ban. Telegram's bot API is free and needs no server.
- **No agent framework (LangChain etc).** The loop is about 30 lines. Writing it by hand shows what frameworks hide.
- **The model gets the current date/time in every prompt.** It has no clock; "Thursday" means nothing without it.
- **"Never guess" rule + `null`.** Gives the model an honest way out instead of inventing a time.
- **Normalize in code, don't trust the prompt.** The prompt asks for `YYYY-MM-DDTHH:MM`, but the model once sent a space instead of the `T`, which silently breaks text comparisons in SQL. Times are now reformatted in code before they touch the database.
- **Tell the truth about failures.** If an event is saved but no reminder could be scheduled, the tool result carries a warning, so the bot does not cheerfully claim success.
- **Retry with backoff** (`call_model` in `agent.py`) for 503/429 errors from the Gemini API.
- **Tool errors are returned to the model as data**, so it can retry or explain instead of crashing.
- **Step limit of 6** in the agent loop so a confused model can never loop forever.
- **Only the chat ID in `.env` is allowed to talk to the bot.** Anyone can message a bot; the code ignores everyone else.
- **Destructive actions are guarded in code.** `cancel_event` (via the model) only records a pending request. A plain `yes` from me, handled before the model sees it, does the actual delete. A prompt rule alone can be ignored by a model; code cannot.
- **Plain commands skip the AI** (`/list`, `/today`, `/cancel`). Use code for what code can do; AI is slow, can fail and has rate limits. The briefing is plain code for the same reason.
- **Network calls are allowed to fail.** `send` and `get_updates` catch errors, log them, and carry on. A reminder is marked sent only if `send` returned success, so a dropped connection means "try again", not "silently lost".
- **One copy only.** A lock file (`bot.lock`, via `fcntl.flock`) stops a second `bot.py` from starting. The OS drops the lock automatically if the process dies, so a crash never leaves a stale lock behind.
- **Free-tier privacy note:** Google says free-tier requests may be used to improve their products. Do not send private documents or passwords through this bot.
- **The repo is public.** Secrets live only in `.env`, which is git-ignored. Before pushing, check `git status` and `git ls-files` for `.env`, `.venv`, `agent.db`.

## Things that went wrong while building (and the fix)

| Symptom | Cause | Fix |
|---|---|---|
| `zsh: command not found: python` | macOS only has `python3` outside a venv | Use `python3`, or activate the venv first |
| `can't open file ... No such file` | Typo in file name (`char` vs `chat`) | `ls`, then `mv` to rename |
| `NameError: name 'cat' is not defined` | A terminal command got pasted into a `.py` file | Terminal commands go in the terminal, code goes in the editor |
| `IndentationError` | Pasted code lost its leading spaces | Re-paste the whole file; check with `python -m py_compile` |
| `TypeError: 'NoneType' object is not iterable` | A function was missing its `return` line | Add the `return` |
| Empty output from `get_chat_id.py` | Messaged BotFather instead of my own bot | Message the new bot, then rerun |
| Junk or duplicate events from corrections like "actually 4:40" | Every message was processed in isolation, no way to edit | Added the tool-using agent and short-term memory |
| `'None'` shown for slash typos | Unknown `/commands` fell through to the AI | Unknown `/...` now gets a "Unknown command" reply |
| Model invented a time for "evening" | Rule left to the model's judgment | Fixed the day-part times in the prompt |
| `503 UNAVAILABLE` | Gemini overloaded | Retry with backoff |
| "pee after 5 mins" saved but never notified | All reminder offsets were already in the past | Added a "now" reminder at event time |
| "when are my reminders?" had no real answer | No tool returned reminder times, so the model would improvise | Added the `list_reminders` tool, and a rule to only state facts from tool results |
| `/today` replied "Unknown command" | The `/today` check sat below the catch-all `/` check, or the bot was not restarted | Order matters: specific commands first, catch-all last; restart after edits |
| Bot crashed with `ReadTimeout` when Wi-Fi dropped | Network calls in `bot.py` were not wrapped in error handling | `send` and `get_updates` now catch network errors and retry |
| Reminder for "drink water" never arrived | The model sent the time with a space (`2026-11-01 15:08`) and the "now" reminder was missing from `OFFSETS`, so zero reminders were scheduled | Normalize times in code, added the "now" reminder, added a warning when nothing is scheduled |
| Repeated `KeyError` / `HTTP 409: terminated by other getUpdates request` | Two copies of `bot.py` were polling the same Telegram token | Kill every copy (`pkill -f bot.py`), start one; added the `bot.lock` guard; log Telegram's real error text instead of a vague message |
| A stray empty file named `reminder-agent` got committed | An accidental shell redirect | `git rm reminder-agent` |
| Occasional single `ReadTimeout` every few minutes in the log | Dorm Wi-Fi stalls an odd request; the next poll succeeds | Normal. Messages are not lost (Telegram queues them) |

## Troubleshooting checklist

1. Is exactly one bot running? `pgrep -fl bot.py`
2. Did I restart after editing? Python reads the code only at startup.
3. Syntax or indentation error? `python -m py_compile db.py agent.py bot.py briefing.py`
4. What does the log say? Telegram errors now print their description (`HTTP 409`, `HTTP 429`, ...). `ReadTimeout`/`ConnectionError` means the network, not the code.
5. Is the data right? Query `agent.db` with `sqlite3` (commands above).
6. Did the model call a tool? The terminal prints every `tool call:` and `result:`.

## Known limitations

- Only runs while the terminal with `bot.py` is open and the laptop is awake and online. Reminders missed while off are sent late only if the event has not started yet.
- Chat memory (last 12 turns) lives in RAM and is lost on restart. Events, reminders and state are in SQLite and persist.
- Duplicate detection is exact (same title ignoring case, same time). "data structures quiz" vs "dsa quiz" at the same time is not caught.
- Command matching uses `startswith`, so `/listy` is treated as `/list`.
- Single user only, single timezone, text messages only (photos and stickers are ignored).
- Free-tier rate limits apply; heavy use will hit `429`. One message can cost 2 or 3 API calls.
- The model can still mis-parse unusual messages. Always read the echoed result.
- The lock only protects against a second copy on the same machine.

## Status

- [x] Python, venv, project setup
- [x] Telegram bot sends and receives
- [x] Gemini key and first LLM call
- [x] Structured extraction (message to JSON) with the current-date trick
- [x] SQLite storage and reminder scheduling
- [x] Scheduler loop: reminders arrive on their own
- [x] `/list` and `/cancel`
- [x] Tool-using agent (add, list, cancel, reschedule, list reminders)
- [x] Retry on 503/429, "now" reminder
- [x] Daily briefing and `/today`
- [x] Duplicate protection (exact match)
- [x] Network failure handling, honest logging of Telegram errors
- [x] Single-instance lock
- [ ] Confirm-before-delete: code written, manual tests skipped. Will be covered by automated tests instead (create, "cancel it", yes / no / maybe, and the "do not ask me, just do it" attack, where the event must survive until a bare `yes`).
- [ ] `requirements.txt` and `.env.example`
- [ ] Automated tests
- [ ] Chat memory that survives restarts
- [ ] Logging to a file

## Ideas for next time

- Automated tests that need no Gemini calls: reminder scheduling, skipping past reminders, `due_reminders` rules, the delete guard, time normalization. Plus a small "eval" script of tricky messages (typos, Bangla, group-chat noise) to measure prompt changes.
- `requirements.txt` (`pip freeze`) and `.env.example` so a stranger can clone and run it.
- Persist chat memory in SQLite so it survives restarts.
- Log every message, tool call and error to a file.
- Reuse one `requests.Session` for Telegram calls and shorten the read timeout, to cut down on the occasional timeout.
- Exact command matching, and near-duplicate detection (ask "is this the same as event X?").
- Quiz-me feature: save syllabus notes, have the model generate questions, track which ones I miss, spaced repetition.
- Handle photos: forward a notice screenshot and extract the event from the image.
- Try a local model (Ollama) in place of Gemini and compare tool-calling quality.
- Run it without the laptop: start at login with `launchd`, or GitHub Actions on a schedule (free, but timing is fuzzy, a few minutes late; check the current free minutes), or Cloudflare Workers (JavaScript rewrite, precise timing).
- Rebuild the same flow in n8n and compare it with the hand-written version.

## Workflow reminder

Commit after every step that works:

```
git add .
git commit -m "what changed"
git push
```

If an edit breaks something: `git diff` shows what changed, `git log --oneline` shows past snapshots. Before committing, `git status` should never list `.env`, `.venv`, `agent.db`, `bot.lock` or `__pycache__`.