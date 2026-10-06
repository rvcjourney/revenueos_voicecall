# Brief: connect this voice platform to RevenueOS Brain

You are working in the MOTMVoice repository (FastAPI backend, Celery workers, LiveKit voice agent, React dashboard). This brief asks you to add one thing: a small API through which **RevenueOS Brain** can run a calling campaign here with a single request. It was written on 2026-10-06 by the agent that built the same integration for the email platform, after a short read of this repository. Treat what it says about this codebase as leads to verify, not as facts.

## What RevenueOS is and why this matters

RevenueOS is MOTM's internal operating system for delivering customer engagements. Its "Planning Brain" holds the knowledge about each client (who they sell to, what they offer, which accounts to approach) and decides what outreach to run. The execution tools (email, AI calling, WhatsApp) each sit behind an API that Brain calls. Brain is ordinary server code making HTTPS requests; it has no browser session and no person clicking.

This repository is the AI calling tool. Today a person registers, creates an agent, creates a campaign, uploads a CSV and clicks Launch. Brain needs to do the equivalent without the dashboard, and to learn what happened on each call so it can update the CRM and decide the next step.

The owner works in plain language, is not a backend engineer, and tests by sending a payload and looking at the response. A response that says exactly what happened and what to do next is worth more to them than an elegant internal design.

## The pattern to follow

The email platform solved the same problem, and the owner now thinks in its terms. Follow its shape unless this codebase gives you a reason not to, and say so when you deviate.

The email side ended up with one "launch" route that does everything for a campaign, plus small routes for the steps that cannot finish inside one request. Its ideas, in order of importance:

1. **One request, whole job.** Account, sender, recipients, campaign and start in one payload. The owner asked for this explicitly after trying a multi-call flow.
2. **Two references.** `client_reference` identifies the client account; `reference` identifies the campaign. The same `client_reference` reuses the account; a new `reference` makes a new campaign. Repeating a `reference` with the same content creates nothing and returns the original result with `duplicate: true`; the same `reference` with different content is refused (409). This was added after the owner accidentally created three empty accounts by sending new references without a client id, so make `client_reference` hard to forget.
3. **Key-only authentication.** Brain sends one shared secret in a header (`X-RevenueOS-Key` on the email side), compared in constant time, minimum 32 characters, checked at boot. The route acts as a configured user/organization that is fixed in server settings and never taken from the request. Without the settings the route answers 503 rather than being open.
4. **Off by default.** Each capability that spends money or contacts real people has its own on/off setting.
5. **Composition, not a second implementation.** The routes call the services the dashboard already uses, so validation, limits and safety rules stay in one place.
6. **A status the caller can act on.** The response carries a field such as `start_status` with a small fixed vocabulary (`started`, `pending`, `blocked`, `failed`, `already_started`) and, when not started, the reason in plain words.
7. **Partial success is reported, not hidden.** A bad recipient is listed in `recipients_rejected` and the rest go through. A sender that fails to connect does not undo the account.

The email implementation is in the sibling repository at `D:\MOTM Diagnose\RevenueOS\email\Email-Outreach-Platform`. The files worth reading are `backend/app/modules/integrations/revenueos_launch.py`, `backend/app/api/v1/integrations.py`, and `docs/adr/0019` to `0024`, which record each decision and its consequences. Read them for the reasoning; do not copy code, since that project uses different tables, a synchronous session and its own role model.

## How the email concepts map here

This is my reading; confirm each row in the code.

| Email platform | This platform, as far as I could see |
|---|---|
| User + workspace per client | User + organization (`org_id` scoping; `/api/auth/register` creates an org and uses OTP email verification) |
| SMTP sender mailbox | SIP trunk / phone number (`app/api/sip_trunks.py`, including `connect-vobiz`; credentials are encrypted) |
| Recipients (email + profile) | Campaign contacts: `name`, `phone`, `email`, `company`, `custom_fields`, today only via CSV/Excel upload in `POST /api/campaigns/{id}/contacts` |
| Emails + objective | The AI agent: `system_prompt`, `welcome_message`, `language`, `voice_id`, `llm_model` (`AgentCreate`) |
| Schedule | `calling_window_start/end`, `calling_days`, `timezone`, `calls_per_minute`, `max_retries`, `retry_after_minutes` |
| Start | `POST /api/campaigns/{id}/launch`, which checks the org is active and has credits |
| Standard vs hyper-personalized | Possibly normal vs `is_prime` ("Prime Calling", which requires a Company Profile). I did not trace what Prime does; find out before mapping it |

Three things here have no email equivalent and need a deliberate decision each: **credits and billing** (launch refuses without credits), **agent access approval** (members need approved access to an agent; admins do not), and the **DNC list**.

## What to build

A launch route for Brain, key-authenticated, that for one payload: finds or creates the client's organization and user under `client_reference`; uses or connects the phone number; creates or reuses the agent with the script Brain supplies; creates the campaign under `reference`; adds the contacts from JSON (not a file upload); and, when asked and enabled, launches it. Then the read side: a way for Brain to fetch a campaign's status and each call's outcome, summary and transcript, because without results Brain cannot close the loop. The email platform still lacks that read side and it is the largest gap there; do not repeat it.

Cover the same account scenarios the owner tests with on email: a new account; the same account with a new campaign; the same account with the same number; the same account with a different number. Give the owner one example payload per scenario when you report.

Useful extras, if they fall out naturally: pause for a running campaign (email has none and the owner cannot stop anything through the API), and a webhook or polling cursor for finished calls.

## Decisions that belong to the owner

Ask before building these; each changes the design and the owner has changed their mind on similar points before, so present options with consequences rather than a recommendation alone.

- **Who pays.** Does a Brain-created organization get credits automatically, share MOTM's own, or need a person to add them? A launch that silently returns "no credits" is useless to Brain.
- **Whose phone number.** Does each client bring a Vobiz trunk in the payload (credentials travelling in a request), or do Brain's campaigns use numbers already connected by a person? On email the owner first said "never send credentials" and later chose to send them.
- **Agent per campaign or per client.** Does Brain send a full script each time, or pick an existing agent by id?
- **Auto-launch.** On email the owner removed the manual Start for standard campaigns but kept a human approval for AI-written ones. A wrong call is harder to take back than a wrong email, so do not assume.
- **One organization per client, or one MOTM organization with a campaign folder per client.** The existing register flow, billing and RLS all assume the former is a paying customer.
- **Login for the client.** Does anyone at the client ever log in here? On email the owner wanted the new user to log in immediately.

## Constraints

- **Real phone calls, real money, real people.** Never place a call to verify your work. Test with mocks and a throwaway database; if the owner wants a live test, it is to their own number, by them. Respect the calling window, DNC list, concurrency caps and call-duration guard that already exist; the launch route must not offer a way around any of them.
- **Do not run migrations or deploy.** Prepare an Alembic migration if the schema must change, explain what it does, and let the owner apply it. On the email project a "no migration needed" claim turned out wrong once a real database was involved, so test against a real Postgres before saying it.
- **This project's own conventions win.** It uses Alembic, async SQLAlchemy and JWT; the email project uses raw Supabase migrations and a different auth model. Read this repository's README and existing patterns first. There is no AGENTS.md or CLAUDE.md here that I saw.
- **Tenant isolation.** A key that can create organizations must never be able to read or act in an organization it did not create or was not given. Write a test that proves a second client's data is invisible.
- **Secrets.** The owner tends to paste keys and passwords into chat and into requests. Never echo a secret back, keep them out of logs and error bodies (FastAPI's default 422 echoes the request body, which leaked an SMTP password into responses on the email side), and tell the owner when something they pasted should be rotated.
- **Shared server.** Production runs on a VPS with about two dozen other Docker projects and a full swap file. Do not add services casually; fixed project names and ports matter there.

## Lessons from the email build that will save you time

- The first live run found bugs that mocked tests could not: a database role left switched after a mailbox operation, and missing role grants on a newer Supabase. Tests against a real throwaway Postgres caught the next ones before the owner did. Use them here for anything touching RLS or roles (migrations `0025` and `0033` here enable RLS).
- Work that finishes in a background worker cannot complete inside the request. Email solved this by committing what was stored, waiting a bounded few seconds, and otherwise returning `pending` with "send the same request again". Launching a calling campaign is already asynchronous here, so decide what "started" honestly means.
- Idempotency keyed on content hashes breaks when you add a field with a default. Email kept old references valid by adding new fields to the hash only when present.
- Report results in the owner's terms: what was created, what was reused, what was refused and why, and the one next action.

## What done looks like

The owner can send one documented payload per scenario and get a response that says what happened. Repeating any payload creates nothing new. A second client cannot see the first. Brain can read call outcomes for a campaign it launched. Every capability that calls real people is off until a setting turns it on. There are tests for the payload rules, the key and switches, idempotency and tenant isolation, with the database-dependent ones run against a real Postgres. A short decision record explains what was decided and what was left out. Nothing was deployed, no migration was applied and no real call was placed by you.

When you report back, lead with what works and what the owner must do next, list anything you could not verify, and give the example payloads.
