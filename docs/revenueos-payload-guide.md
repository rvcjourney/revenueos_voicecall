# RevenueOS Brain → Voice calling: payload guide (v2)

For whoever builds the requests Brain sends. Base URL: `https://revenueoscall.b2botix.ai`.

Status: v2 passes the platform's automated tests (7 November 2026) but has not yet placed a live call. This line will be updated after the first live test.

**v2 (November 2026)** follows the main voice platform's redesign: calls run on Sarvam only, and the per-contact script comes from `{placeholders}` in the agent instead of Prime Calling. Compared with v1:

- **Removed:** `company_profile`, `prime`, `agent.voice_provider`, and `script_personalised` / `script_error` in call results. Sending `company_profile` or `prime` is refused with 422.
- **Added:** `agent.variables`, `agent.speech_pace`, `agent.transfer_number`, top-level `webhook_url`, and `placeholders_unfilled` in the response.
- **Changed:** `agent.voice_id` is a Sarvam voice for the agent's language; blank picks the language's default voice. ElevenLabs voices are not available for Hinglish, Hindi or English.

## The request

```
POST /api/integrations/revenueos/launch
X-RevenueOS-Key: <the key>
Content-Type: application/json
```

One request does everything: account, phone number, webhook, agent, campaign, contacts and the start.

## The two references

| Field | Identifies | Same value again | New value |
|---|---|---|---|
| `client_reference` | The client (one account) | Reuses that client's account, number and webhook | Creates a new client account |
| `reference` | One campaign | Repeats that campaign; nothing is created twice | Creates a new campaign |

Keep `client_reference` fixed per client forever, and use a fresh `reference` for every campaign.

## A complete first request

```json
{
  "client_reference": "motm-tech",
  "reference": "motm-marketing-motors-20",
  "user": {
    "email": "owner@client.example",
    "password": "choose-a-strong-password",
    "full_name": "MOTM Technologies",
    "company_name": "MOTM Technologies"
  },
  "phone_number": {
    "auth_id": "MA_XXXXXXXX",
    "auth_token": "<Vobiz auth token>",
    "did": "+918065382389"
  },
  "webhook_url": "https://brain.example.com/hooks/voice-calls",
  "agent": {
    "name": "Simran",
    "language": "hinglish",
    "voice_id": "simran_enhi_customer",
    "welcome_message": "{time_greeting} {name} ji, main Simran bol rahi hoon MOTM Technologies, Pune se. Kya aapke paas do minute hain?",
    "system_prompt": "You are Simran, calling for MOTM Technologies, a Pune company that does industrial marketing for manufacturers: market visibility, Account-Based Marketing and multi-channel outreach. You are speaking to {name} at {company}, which makes {products}. Keep the whole conversation about marketing. Find out how they get new enquiries today, then offer a short follow-up meeting with the MOTM team. Be polite and brief, and do not push if they are not interested.",
    "variables": { "products": "industrial products" },
    "speech_pace": 1.0
  },
  "campaign": { "name": "Marketing pitch - motor manufacturers" },
  "contacts": [
    {
      "name": "Chinmay",
      "phone": "+918484876325",
      "company": "Genuine Motors Manufacturers",
      "website": "https://genuinemotors.example",
      "custom_fields": { "products": "3-phase induction motors", "city": "Pune" }
    }
  ],
  "auto_start": true
}
```

Response (trimmed):

```json
{
  "duplicate": false,
  "account": { "status": "created", "organization_id": "…", "login_email": "owner@client.example" },
  "webhook": { "status": "saved", "url": "https://brain.example.com/hooks/voice-calls", "secret": "whsec_…" },
  "phone_number": { "status": "connected", "number": "+918065382389" },
  "agent": { "status": "created", "id": "…", "name": "Simran" },
  "campaign": { "id": "…", "name": "Marketing pitch - motor manufacturers", "status": "running", "contacts_added": 1 },
  "contacts_rejected": [],
  "placeholders_unfilled": [],
  "start_status": "started",
  "start_reason": null,
  "next_action": "Read the results."
}
```

**Store `webhook.secret` when it appears.** It is shown only the first time a webhook is set for the client, and cannot be read back.

## How the per-contact script works: placeholders

Write `{name}`-style placeholders in `welcome_message` and `system_prompt`. For each call they are filled, first match wins, from:

1. **The contact:** `name`, `email`, `company`, `website`, and every key in `custom_fields`.
2. **The agent's `variables`:** defaults used when a contact has no value.
3. **System values:** `{time_greeting}` ("Good morning/afternoon/evening" in the campaign's timezone) and `{current_date}`.

Matching ignores case, spaces and underscores, so a `custom_fields` key `"Product Line"` fills `{productLine}`.

A placeholder with no value anywhere is **spoken as nothing**. The launch response lists any such placeholder in `placeholders_unfilled`, with how many contacts lack it, for example `[{"placeholder": "products", "contacts_without_value": 3}]`. Add a default in `variables` to avoid gaps.

## Scenarios

| # | Scenario | `client_reference` | `reference` | Send | Response shows |
|---|---|---|---|---|---|
| 1 | New account, new campaign | new | new | everything | `account: created`, `phone_number: connected`, `agent: created` |
| 2 | Existing account, new campaign | same | new | `user`, `agent`, `campaign`, `contacts` | `account: reused`, `phone_number: reused` |
| 3 | Different voice, language or script | same | new | as 2, with the changed `agent` | `agent: created` |
| 4 | A second phone number | same | new | as 2, plus `phone_number` with the new `did` | `phone_number: connected` |
| 5 | Set, change or remove the webhook | same | new | as 2, plus `webhook_url` (`""` removes it) | `webhook.status: saved` / `off` |
| 6 | Store now, start later | any | new | `auto_start: false` | `start_status: pending` |
| 7 | Start a stored campaign, or resume a paused one | same | same | the identical request, `auto_start: true` | `duplicate: true`, `start_status: started` |
| 8 | Same request sent twice | same | same | identical | `duplicate: true`, nothing new |
| 9 | Same reference, changed content | same | same | changed `agent`, `campaign`, `schedule` or `contacts` | HTTP 409 |

Notes:

- **The `user` block is required on every request.** Its `email` must match the account; `password` is only used when the account is first created.
- **An agent is reused** when its name, language, voice, greeting, instructions, variables, pace, call length and transfer number all match an earlier one.
- **The webhook can only change together with a launch.** There is no separate endpoint; send `webhook_url` with the next campaign.
- **What counts as "content" for 409:** `agent`, `campaign`, `schedule` and `contacts`. Not counted: `user`, `phone_number`, `webhook_url`, `auto_start`.

## Field reference

| Block | Field | Required | Default | Rules |
|---|---|---|---|---|
| top level | `client_reference`, `reference` | Yes | | 1–120 characters; letters, digits, `.` `_` `:` `-`; starts with a letter or digit |
| top level | `webhook_url` | No | unchanged | Public `https://` URL; `""` turns it off |
| top level | `auto_start` | No | `true` | `true` dials immediately |
| `user` | `email`, `password`, `full_name`, `company_name` | Yes | | Password 6–128 characters; `phone` optional |
| `phone_number` | `auth_id`, `auth_token`, `did` | First launch | | `auth_id` is the Vobiz API Auth ID (starts `MA_`) |
| `agent` | `name` | No | campaign name | Up to 255 characters; a label |
| `agent` | `language` | No | `hinglish` | See the table below |
| `agent` | `voice_id` | No | `""` | A voice ID for that language; `""` = default voice |
| `agent` | `welcome_message` | No | `""` | The first line spoken; up to 5000 characters; placeholders allowed |
| `agent` | `system_prompt` | No | `""` | The agent's instructions; up to 50000 characters; placeholders allowed |
| `agent` | `variables` | No | `{}` | Placeholder defaults; text keys and text values |
| `agent` | `speech_pace` | No | `1.0` | 0.7 to 1.5 |
| `agent` | `max_call_duration_seconds` | No | `600` | 30 to 3600 |
| `agent` | `transfer_number` | No | `""` | Number the agent can transfer the call to |
| `campaign` | `name` | Yes | | 1–255 characters; `description`, `goal` optional |
| `schedule` | `calling_window_start`, `calling_window_end` | No | `09:00`, `19:00` | Plain `HH:MM` |
| `schedule` | `calling_days` | No | Mon–Sat | `mon` … `sun` |
| `schedule` | `timezone`, `calls_per_minute` | No | `Asia/Kolkata`, 5 | |
| `contacts[]` | `phone` | Yes | | At least 1, at most 500 contacts per request |
| `contacts[]` | `name`, `email`, `company`, `website`, `custom_fields` | No | | `custom_fields` values must be text |

Unknown fields are refused with 422, naming the field.

## Languages and voices

| `language` | Voices (`voice_id`) |
|---|---|
| `hinglish` | `simran_enhi_customer`, `ishita_enhi_customer`, `shalini_enhi_customer` (female); `sunny_enhi_customer`, `shubh_enhi_companion` (male) |
| `hindi` | `ritu_hi_conversation`, `kavya_hi_conversational`, `simran_hi_conversation` (female); `rahul_hi_conversational`, `aditya_hi_conversational`, `amit_hi_conversational` (male) |
| `english` | `simran_en_conversation`, `neha_en_customer` (female); `dev_en_conversational`, `deven_en_conversation` (male) |
| `marathi` | `ishita_mr_conversational`, `neha_mr_narration` (female); `nilesh_mr_conversation`, `soham_mr_narration` (male) |
| `telugu` | `kavitha_te_conversation`, `pooja_te_conversation` (female); `tarun_te_narration` (male) |
| `kannada` | `chaitra_kn_conversation`, `suchitra_kn_narration` (female); `chetan_kn_conversation` (male) |
| `punjabi` | `harpreet_pa_narration` (female); `anand_pa_conversation`, `jaspal_pa_banking` (male) |
| `tamil` | `vijay_ta_narration`, `gokul_ta_narration` (male) |
| `bengali` | `roopa_bn_conversational` (female); `arnab_bn_conversation` (male) |
| `gujarati` | `pooja_gu_conversational` (female); `bhavik_gu_conversation` (male) |

This is the list as of November 2026. The platform owner can switch languages on or off and change voices in the admin area, so a voice can be refused later; the launch then answers `start_status: blocked` with the reason.

## Results: webhook or polling

### Webhook (recommended)

When `webhook_url` is set, the platform POSTs one `call.completed` event per finished call, retrying on failure (after 30 s, 2 min, 8 min and 32 min).

```json
{
  "event": "call.completed",
  "call_id": "…",
  "campaign_id": "…",
  "phone_number": "+918484876325",
  "direction": "outbound",
  "status": "completed",
  "outcome": "interested",
  "summary": "…",
  "duration_seconds": 67,
  "started_at": "…",
  "ended_at": "…",
  "recording_url": "…",
  "extracted_data": {},
  "contact": { "name": "Chinmay", "email": null, "company": "Genuine Motors Manufacturers", "custom_fields": { "…": "…" } },
  "transcript": [ { "speaker": "agent", "text": "…" }, { "speaker": "user", "text": "…" } ]
}
```

- **Match it to a campaign** with `campaign_id`, which is `campaign.id` from the launch response.
- **Verify every request.** The header `X-MOTM-Signature: t=<unix time>,v1=<hex>` holds an HMAC-SHA256 of `"<t>.<raw body>"` keyed with the webhook secret. Recompute it on the raw body and compare; reject old timestamps.

### Polling

The same data is available from the endpoints below, for back-filling or when no webhook is set.

## Endpoints

All need `X-RevenueOS-Key`. `{reference}` is the campaign's `reference`; `client_reference` is required on the last three, and a campaign asked for under the wrong client answers 404.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/integrations/revenueos/launch` | Everything above |
| GET | `/api/integrations/revenueos/campaigns/{reference}?client_reference=…` | Campaign state, contacts left, calls by outcome |
| GET | `/api/integrations/revenueos/campaigns/{reference}/calls?client_reference=…` | Each call's result; `since`, `limit` (1–200, default 100), `include_transcript` |
| POST | `/api/integrations/revenueos/campaigns/{reference}/pause?client_reference=…` | Stop placing new calls |

The calls answer ends with `next_since`; pass it back as `since` to get only what changed. There is no resume endpoint: send the original launch again with `auto_start: true`.

### Call result fields

Each item in the calls answer (and each webhook event) carries:

| Field | Meaning |
|---|---|
| `status` | The call itself: `initiated`, `ringing`, `connected`, `completed`, `no_answer`, `busy`, `failed`, `cancelled` |
| `outcome` | The verdict on the conversation: `interested`, `not_interested`, `callback_requested`, `wrong_number`, `do_not_call`, `voicemail`, `no_answer`, `call_dropped`, or `pending` until classified |
| `summary` | A short written summary of the conversation |
| `duration_seconds`, `started_at`, `answered_at`, `ended_at` | Timing (the webhook has no `answered_at`) |
| `extracted_data` | Details the agent collected, such as an email or a meeting time |
| `transcript` | Lines with `speaker` (`agent` or `user`) and `text` |
| `finished` | Calls answer only: `true` once the call will not change again |
| `has_recording` / `recording_url` | Whether a recording exists (calls answer) / its address (webhook) |

`call_dropped` means the line cut off mid-conversation without a clear answer either way; treat it as worth retrying by hand, not as a refusal.

The campaign `status` is one of `draft`, `scheduled`, `running`, `paused`, `completed`, `failed`. A campaign can also be paused by the platform itself, for example when the platform owner switches off a language.

## `start_status`

| Value | Meaning | Next |
|---|---|---|
| `started` | Running and handed to the dialler | Wait for webhooks, or poll |
| `already_started` | Already running, or finished | Same |
| `pending` | Stored, not started | Send the same request with `auto_start: true` |
| `blocked` | Could not start; `start_reason` says why | Fix it and send the same request again |
| `failed` | Stopped with an error | Fix it, then use a new `reference` |

## Errors

| HTTP | When |
|---|---|
| 401 | `X-RevenueOS-Key` missing or wrong |
| 409 | Reference reused with different content or under another client; `client_reference` with a different email; email already used by another account |
| 422 | Unknown field (including the removed `company_profile` and `prime`), bad value, or every contact refused |
| 503 | Integration not configured, launch switched off, or `auto_start: true` while auto-start is off |

Partial success returns 200: refused contacts are listed in `contacts_rejected`; a number that fails to connect keeps the account and returns `phone_number.status: "failed"` with `start_status: "blocked"`; a webhook URL that is not public HTTPS returns `webhook.status: "failed"` and the campaign still starts.

## Good to know

- **No wait before each dial any more.** Without Prime Calling there is no script-writing step.
- **One call at a time per client**, whatever `calls_per_minute` says.
- **Unanswered calls are not retried.** Transcripts and recordings are deleted after 45 days.
- **No editing a campaign after launch**: use a new `reference`.
- **The password cannot be changed through the integration.**
