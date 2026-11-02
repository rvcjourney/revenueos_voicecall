# Working on QuickHowl safely

Every change is tried on your laptop first. It reaches the live site (app.quickhowl.com) only when it is pushed to `main`.

Your laptop runs its own private copy of QuickHowl with its **own empty database**. Nothing you do locally touches real customers or real data.

---

## One-time setup

You need **Docker Desktop** (installed) and **Node.js** (installed).

1. **Settings files.** These are private and never uploaded to GitHub:
   - `backend/.env.dev`: backend keys
   - `agent/.env.dev`: call-agent keys
   - `frontend/motm-voice-frontend/.env.local`: points the website at `http://localhost:8000`

2. **Copy the current LiveKit keys from the server.** The keys on your laptop are old.
   On the server, open `/opt/quickhole/agent/.env`. Copy `LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` into **both** `backend/.env.dev` and `agent/.env.dev`.
   Also copy `DEFAULT_SIP_TRUNK_ID` and `DEFAULT_SIP_CALLER_ID` from the server's `backend/.env` into `backend/.env.dev`. If `SARVAM_API_KEY` differs from your local one, copy it into both files too.
   Do **not** copy `DATABASE_URL`, `SECRET_KEY`, `FERNET_KEY` or `AGENT_WEBHOOK_SECRET`. The local ones are intentionally different.

3. **Start everything** (see "Every day" below). Then create your local super-admin:
   ```
   docker compose -f docker-compose.dev.yml exec api python -m scripts.create_platform_admin --email you@example.com --password YourPassword
   ```
   Log in at http://localhost:5173/ops. Create a plan under **Plans**, then sign up a test company at http://localhost:5173/signup.
   You'll get a real verification email. You can enter that code, or skip it and just log in, since local login doesn't require a verified email.

---

## Every day

**Start** (open Docker Desktop first and wait until it says "running"):
```
docker compose -f docker-compose.dev.yml up -d
cd frontend/motm-voice-frontend
npm run dev
```
Then open http://localhost:5173.

| What | Where |
|---|---|
| Website | http://localhost:5173 |
| Backend API docs | http://localhost:8000/docs |
| Logs | `docker compose -f docker-compose.dev.yml logs -f api worker agent` |

**Stop:** press Ctrl+C in the website window, then run `docker compose -f docker-compose.dev.yml down`.

**Start fresh (wipes all local data):** `docker compose -f docker-compose.dev.yml down -v`

**After a change:**
- Website, backend API and call agent reload by themselves.
- Background jobs (campaigns, emails) need a restart: `docker compose -f docker-compose.dev.yml restart worker beat`
- If `requirements.txt` changed, rebuild: `docker compose -f docker-compose.dev.yml up -d --build`

---

## The workflow: test first, then go live

1. **Ask for a change.** Claude makes it on a separate branch, not on `main`, and runs the automated tests.
2. **Try it locally** at http://localhost:5173. If it affects calls, place a test call to your own phone.
3. **Happy? Say "push".** The branch is merged into `main` and pushed. GitHub runs all the tests again and, if they pass, updates the live site automatically.
4. **Not happy?** Ask for fixes and repeat step 2. Nothing has gone live yet.

Optional: push the branch and open a Pull Request on GitHub. The tests run on it without deploying, and you merge it when they're green.

---

## Test calls from your laptop

Local calls go through the same phone line and LiveKit account as the live site. The laptop's call agent registers under a different name (`voice-call-agent-dev`), so:
- calls you start locally are handled by your laptop, and
- your laptop never picks up a live customer's call.

Things to know:
- Test calls cost real Sarvam and Vobiz minutes, the same as live calls.
- **Recordings don't appear locally.** Vobiz sends them to the live server. Transcript, outcome and minutes all work.
- The call agent must be running. Check with `docker compose -f docker-compose.dev.yml logs agent`, which should say "registered worker", not "failed to connect".
