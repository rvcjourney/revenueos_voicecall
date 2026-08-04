# Changes Log

A simple record of what was asked for and what was done, in plain language.

---

## 1. Campaigns page — viewing campaigns inside a folder

**What you asked for:**
First, you wanted that clicking a company folder should show that folder's campaigns right there, instead of the campaign list appearing all the way at the bottom of the page.

Then you asked for something more specific: clicking a folder should feel like actually going "inside" that folder — a dedicated screen just for that folder's campaigns — with a way to go back to the main folder list and open a different folder afterward.

**What was done:**
- First pass: clicking a folder expanded its campaigns directly underneath that folder's box.
- Final version: clicking a folder now takes you to its own page showing only that folder's campaigns, with the same filters (All, Active, Paused, Completed, Draft) and search box. A "Back to folders" link at the top takes you back to the full folder list, and you can click into any other folder the same way.
- Nothing about how campaigns are fetched, filtered, or counted was changed — only how they're displayed.

---

## 2. Billing — added to the sidebar

**What you asked for:**
Add a "Billing" section to the sidebar where you could eventually handle payments. No real payment processing yet — just the screen/UI for it. You also asked for a list of the important things needed for payment to be shown on the page.

**What was done:**
- Added a new "Billing" item in the sidebar, next to Settings.
- Built a new Billing page with:
  - Current plan and credit usage (this part shows real usage data, same as before).
  - A payment method section (add/view a card — UI only, doesn't actually charge anything).
  - A billing details section (billing email, company name, address, tax ID, currency).
  - An invoice history section (empty for now, will fill up once real invoices exist).
  - A checklist showing what's typically needed before payments can go live (payment method, billing email, address, organization verified, tax ID).
- Every button on this page is a preview — clicking "Save," "Change plan," etc. shows a message saying it isn't connected yet. No real payment logic was added.

---

## 3. Billing — making it look better

**What you asked for:**
The first version of the Billing page didn't look good — you asked for smaller, tighter boxes and a look consistent with the rest of the app.

**What was done:**
- Rebuilt the page using the same compact card style as pages like Phone Numbers and Do-Not-Call list.
- Removed the oversized empty boxes and replaced them with small, simple placeholder lines.
- Made section titles and spacing consistent with the rest of the app instead of using a different, bulkier layout.

---

## 4. AI Agents — changing the icon

**What you asked for:**
Change the little logo/icon shown on each AI agent box and in the sidebar's "AI Agents" link — nothing else about how agents work.

**What was done:**
- Replaced the old robot icon with a headset icon (you picked this from a few options) in two places: on every agent's card, and next to "AI Agents" in the sidebar.
- Nothing about creating, editing, or managing agents was touched.

---

## 5. Phone Numbers page — making it look better

**What you asked for:**
The Phone Numbers page (under Admin) didn't look attractive — you asked for a visual refresh without touching any of the underlying functionality (assigning numbers, test calls, etc. all had to keep working exactly the same).

**What was done:**
- Each phone number now shows as a card with a colored strip on top (green if active, grey if inactive) and a phone icon, similar to the styling used on other pages like Campaigns and AI Agents.
- The "User Access" section (where you assign numbers to team members) is now in its own clearly separated box instead of blending into the rest of the card.
- People assigned to a number now show up with a small circular avatar with their initials, instead of plain text.
- The "no one assigned yet" message now shows as a neater placeholder box instead of plain text.
- All the actual features (assigning access, removing access, testing a number, connecting a new number) work exactly as before — only the appearance changed.

---

## 6. Calls — filling in the "Extracted data" tab

**What you asked for:**
On a call's detail page, the "Extracted data" tab always said "No structured data." You asked for it to actually show useful information pulled from the call — the caller's email, phone number, and what they want (their requirements) — without changing any existing screen, API, or feature.

**What was done:**
- Found the reason the tab was always empty: nothing in the whole app ever filled it in. The spot for this data existed in the database and the screen already knew how to display it — there was just no code writing anything into it.
- After each call ends, the voice agent already sends the call's outcome (interested / not interested / etc.) and a short summary to the backend using AI (Groq). We extended that same step to also ask the AI to pull out, only if the caller actually said it:
  - Caller's name
  - Caller's email
  - Caller's phone/callback number
  - What they want (their requirements — product, design, service, etc.)
  - Budget, if mentioned
  - Whether they're the decision-maker, if that was clear
- The AI is told to leave a field blank rather than guess — so a short call with no useful info just shows fewer fields, never made-up ones.
- Added a small backend field so this new information can travel from the agent to the database, and made the database save it. Nothing about how outcomes, summaries, or transcripts are saved was changed — this was only added on top.
- The screen itself needed zero changes — it already knew how to display whatever fields show up in this data, so the new fields just appear automatically once a call produces them.
- Per your instruction, the wording never names which AI voice/speech provider is used anywhere.

**How to see it working:** place or wait for a new call where the caller actually says their email/number/requirements out loud — very short calls (under ~8 words from the caller) are skipped by design, same as before this change.

---

## Summary

Across entries 1–5, the rule you set was the same every time: **change how things look, not how they work.** No API calls, data logic, or existing features were altered — only layout, spacing, icons, and visual structure.

Entry 6 is different — it's a real logic addition (the AI now extracts and saves new information after each call), but it was still built to leave every existing feature, screen, and API response untouched.
