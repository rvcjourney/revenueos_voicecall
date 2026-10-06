# RevenueOS Brain integration

Decision record and usage guide. Written 2026-10-06.

RevenueOS Brain can run a calling campaign on this platform with one request and read back what happened on each call. Code: `backend/app/api/revenueos.py` (routes) and `backend/app/integrations/revenueos.py` (logic).

## Turning it on

Everything is off until these are set in `backend/.env`. Restart the API after changing them.

| Setting | What it does | Default |
|---|---|---|
| `REVENUEOS_API_KEY` | The secret Brain sends in the `X-RevenueOS-Key` header. At least 32 characters. Blank: every RevenueOS route answers 503. | blank |
| `REVENUEOS_LAUNCH_ENABLED` | Lets the key create accounts, numbers, agents and campaigns. | `false` |
| `REVENUEOS_AUTO_START_ENABLED` | Lets a launch start calling real people with nobody reviewing it. | `false` |
| `REVENUEOS_MAX_CONTACTS` | Most contacts in one request. | `500` |
| `BILLING_ENABLED` | Credits and payments for the whole platform. Set `false` to switch them off. | `true` |

`PUBLIC_BASE_URL` must already be set, as it is for connecting a number in the dashboard.

Migration `0039_revenueos_integration` must be applied first. It adds two new tables and changes no existing one.

## The four routes

All need the header `X-RevenueOS-Key: <the key>`.

| Route | Purpose |
|---|---|
| `POST /api/integrations/revenueos/launch` | Account, number, company profile, agent, campaign, contacts and start |
| `GET /api/integrations/revenueos/campaigns/{reference}?client_reference=…` | Where the campaign stands |
| `GET /api/integrations/revenueos/campaigns/{reference}/calls?client_reference=…` | Each call's outcome, summary and transcript |
| `POST /api/integrations/revenueos/campaigns/{reference}/pause?client_reference=…` | Stop placing new calls |

Reading and pausing need only the key, not the two launch switches, so a running campaign can always be stopped.

## The two references

- `client_reference` identifies the client. The same value reuses the client's account, numbers and company profile.
- `reference` identifies one campaign. A new value makes a new campaign.

Sending a `reference` again with the same content creates nothing and returns `duplicate: true`. Sending it with different campaign, agent, schedule or contacts is refused with 409.

Both are required. An unknown or misspelt field is refused with 422, naming the field.

## What the response tells you

| Field | Meaning |
|---|---|
| `account.status` | `created` or `reused` |
| `phone_number.status` | `connected`, `reused`, `activated`, `missing` or `failed`, with a `reason` when not usable |
| `agent.status` | `created` or `reused` (the same script reuses the same agent) |
| `campaign` | id, name, status, contacts added; `null` when no campaign was stored |
| `contacts_rejected` | each refused phone with the reason; the rest go through |
| `start_status` | `started`, `already_started`, `pending`, `blocked` or `failed` |
| `start_reason` | why, in plain words, when not simply started |
| `next_action` | the one thing to do next |

`started` means the campaign is marked running and handed to the worker. If the calling window is closed, `start_reason` says so and calls begin when it opens.

## Example payloads

### 1. New account

```json
{
  "client_reference": "client-acme",
  "reference": "acme-2026-10-outreach",
  "user": {
    "email": "owner@acme.example.com",
    "password": "choose-a-password",
    "full_name": "Acme Owner",
    "company_name": "Acme Traders"
  },
  "phone_number": {
    "auth_id": "VOBIZ_AUTH_ID",
    "auth_token": "VOBIZ_AUTH_TOKEN",
    "did": "+912212345678"
  },
  "company_profile": {
    "company_name": "Acme Traders",
    "website": "https://acme.example",
    "what_we_offer": "Wholesale food packaging for restaurants",
    "value_proposition": "Next-day delivery, no minimum order",
    "target_customers": "Restaurant and cloud-kitchen owners",
    "call_objective": "Book a 15 minute call with our sales team"
  },
  "agent": {
    "name": "Riya",
    "language": "hinglish",
    "welcome_message": "Namaste, main Acme Traders se Riya bol rahi hoon.",
    "system_prompt": "You are Riya, a friendly sales assistant for Acme Traders."
  },
  "campaign": { "name": "October outreach" },
  "schedule": {
    "calling_window_start": "10:00",
    "calling_window_end": "18:00",
    "calling_days": ["mon", "tue", "wed", "thu", "fri"],
    "timezone": "Asia/Kolkata",
    "calls_per_minute": 5
  },
  "contacts": [
    { "name": "Asha Rao", "phone": "+919000000001", "company": "Asha Foods", "website": "ashafoods.example" },
    { "name": "Vikram Shah", "phone": "9000000002", "email": "vikram@example.com" }
  ],
  "auto_start": true
}
```

### 2. Same account, new campaign

Same `client_reference`, same `user.email`, a new `reference`. The `phone_number` and `company_profile` blocks can be left out: the client's connected number and saved profile are used.

```json
{
  "client_reference": "client-acme",
  "reference": "acme-2026-11-followup",
  "user": { "email": "owner@acme.example.com", "password": "choose-a-password", "full_name": "Acme Owner", "company_name": "Acme Traders" },
  "agent": { "name": "Riya", "language": "hinglish", "system_prompt": "You are Riya, a friendly sales assistant for Acme Traders." },
  "campaign": { "name": "November follow-up" },
  "contacts": [ { "name": "Meera Nair", "phone": "+919000000009" } ]
}
```

### 3. Same account, same number

As payload 2 with the same `phone_number` block as payload 1. The answer shows `phone_number.status: "reused"`; nothing is connected again.

### 4. Same account, different number

As payload 2 with a `phone_number` block carrying a different `did`. That number is connected for this client and this campaign dials from it. The client now has two numbers.

### Reading results

```
GET /api/integrations/revenueos/campaigns/acme-2026-10-outreach?client_reference=client-acme
GET /api/integrations/revenueos/campaigns/acme-2026-10-outreach/calls?client_reference=client-acme
GET /api/integrations/revenueos/campaigns/acme-2026-10-outreach/calls?client_reference=client-acme&since=2026-10-06T10:15:00.123456Z
```

The calls answer ends with `next_since`. Pass it back as `since` to get only calls that changed after that point. `include_transcript=false` leaves transcripts out; `limit` is 100 by default, 200 at most.

## Decisions

1. **One organization per client.** Numbers, the do-not-call list and the Prime Calling company profile are all per organization.
2. **Vobiz details travel in the payload.** The token is stored encrypted and is never returned or logged. Validation errors on these routes list only the field and the reason, never the value sent.
3. **A number Brain sends goes live without the test call.** The dashboard keeps its test step. Consequence: a wrong Vobiz setup shows up only when the client's calls fail.
4. **Prime Calling is on by default** (`"prime": true`). It needs a company profile with at least `company_name` and `what_we_offer`. A launch without one is answered `blocked` and no campaign is stored.
5. **Calls start immediately** when `auto_start` is true and `REVENUEOS_AUTO_START_ENABLED` is on. With the switch off, such a request is refused whole (503) before anything is created.
6. **The client's user can log in** with the email and password from the payload. The email-code step is skipped for these users because MOTM created the account.
7. **Billing is a platform-wide switch**, not deleted code. `BILLING_ENABLED=false` stops credits and unpaid subscriptions from blocking anyone, makes new sign-ups active at once, and hides the Billing menu, the "subscription inactive" banner and the plan step of sign-up. Minutes are still counted.
8. **The key reaches only what it created.** Every read and action looks the campaign up through both references. A campaign asked for under another client's reference is "not found".
9. **A campaign always dials from the client's own number.** The platform-wide fallback number is never chosen by a launch.
10. **The existing launch rules are reused, not copied.** The dashboard's Launch button and Brain's launch call the same function, so the active-organization check, concurrency limit, calling window and do-not-call list apply to both.

## What was left out

- **Unanswered calls are not retried.** That is how the platform already behaves; the payload has no retry setting.
- **No webhook.** Brain polls the calls route with `since`.
- **No resume route.** To resume a paused campaign, send the original launch again with `auto_start` true.
- **Changing an existing number's Vobiz details.** A number already connected is reused as it is.
- **Changing a user's password.** The password is set when the account is created and ignored afterwards.
- **Recordings.** The calls route says whether one exists; it does not return the audio.

## Things to know

- **Transcripts and recordings are deleted after 45 days.** Brain should read results before then.
- **A company profile sent for a client replaces the previous one**, including for that client's campaigns still running.
- **One call at a time per client.** The platform allows one call in flight per campaign owner, and each client has one user, so a client's campaigns dial one contact at a time whatever `calls_per_minute` says.
- **Organizations that signed up but never paid stay inactive** after `BILLING_ENABLED=false`. A platform admin activates them from the admin area.
- **Existing Razorpay subscriptions keep charging** until they are cancelled in Razorpay. Switching billing off here does not cancel them.
- **A website contact field makes Prime read that site.** Send it as `website` on the contact.
