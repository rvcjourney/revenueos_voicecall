# 🎙️ AI Voice Call Agent

A production-ready outbound/inbound AI voice agent using **LiveKit**, **Deepgram**, and **Groq (Llama 3.3)**.  
Test locally from your browser or make real phone calls via SIP trunking.

---

## 📁 Folder Structure

```
ai-voice-agent/
├── agent.py              ← Main AI voice agent (LiveKit Workers)
├── config.py             ← All settings: models, prompts, voices
├── make_call.py          ← CLI to trigger outbound phone calls
├── test_local.py         ← Test agent in browser (no SIP needed)
├── create_trunk.py       ← One-time SIP trunk setup
├── list_trunks.py        ← List existing SIP trunks
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example          ← Copy to .env and fill in
└── dashboard/            ← Next.js web UI (optional)
    ├── src/
    │   ├── pages/
    │   │   ├── index.tsx         ← Main UI
    │   │   └── api/
    │   │       ├── token.ts      ← LiveKit token generator
    │   │       ├── call.ts       ← Trigger outbound call
    │   │       └── dispatch.ts   ← Dispatch agent to room
    │   └── styles/globals.css
    ├── package.json
    └── .env.local.example
```

---

## 🔑 API Keys You Need

| Service | Purpose | Free tier |
|---------|---------|-----------|
| [LiveKit Cloud](https://cloud.livekit.io) | Real-time voice rooms + SIP | ✅ Yes |
| [Deepgram](https://console.deepgram.com) | STT (speech-to-text) + TTS | ✅ $200 credit |
| [Groq](https://console.groq.com) | LLM (ultra-fast Llama 3.3) | ✅ Yes |
| SIP Provider | Real phone calls (PSTN) | Twilio/Vonage/Vobiz |

---

## 🚀 Quick Start (Local Browser Test — No Phone Needed)

### Step 1 — Clone & Setup Python

```bash
git clone <your-repo>
cd ai-voice-agent

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Step 2 — Configure .env

```bash
cp .env.example .env
# Fill in: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET,
#          DEEPGRAM_API_KEY, GROQ_API_KEY
```

### Step 3 — Start the Agent

```bash
python agent.py start
```

You should see: `Agent started successfully`

### Step 4 — Test in Browser

```bash
# In a NEW terminal (venv active)
python test_local.py
# → Opens your browser, you can talk to the agent directly
```

---

## 📞 Making Real Phone Calls

### Step 1 — Get a SIP Provider

Pick one:
- **Twilio** — https://twilio.com (most popular, $15 to start)
- **Vonage** — https://vonage.com
- **Vobiz** — https://vobiz.com (original project)

Get:
- A DID (phone number) from the provider
- SIP URI (e.g. `sip.twilio.com`)
- SIP username + password

### Step 2 — Update .env

```env
SIP_TRUNK_NUMBER=+1XXXXXXXXXX   # your DID
OUTBOUND_SIP_URI=sip.twilio.com
SIP_USERNAME=your_username
SIP_PASSWORD=your_password
```

### Step 3 — Create SIP Trunk in LiveKit

```bash
python create_trunk.py
# → Prints your SIP_TRUNK_ID, add it to .env
```

### Step 4 — Make a Call

```bash
# Terminal 1: agent running
python agent.py start

# Terminal 2: make a call
python make_call.py --to +91XXXXXXXXXX
```

---

## 🖥️ Dashboard (Optional Web UI)

```bash
cd dashboard
cp .env.local.example .env.local
# Fill in NEXT_PUBLIC_LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET

npm install
npm run dev
# → Open http://localhost:3000
```

---

## ⚙️ Customising the Agent

Edit **`config.py`** to change:

| Variable | What it controls |
|----------|-----------------|
| `AGENT_SYSTEM_PROMPT` | Agent personality & instructions |
| `AGENT_WELCOME_MESSAGE` | First thing the agent says |
| `GROQ_MODEL` | Switch LLM (llama-3.3-70b / llama-3.1-8b) |
| `DEEPGRAM_TTS_VOICE` | Voice (thalia, luna, stella, etc.) |
| `DEEPGRAM_STT_MODEL` | Transcription model (nova-3) |

---

## 🔧 Troubleshooting

### Agent doesn't start
```bash
# Check your .env has all 3 LiveKit values:
# LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
```

### 404 SIP Trunk error
```bash
python list_trunks.py        # see existing trunks
python create_trunk.py       # create a new one
# Then update SIP_TRUNK_ID in .env
```

### Port already in use
```bash
pkill -f "python agent.py"
python agent.py start
```

### No audio in browser
- Allow microphone in browser when prompted
- Check you're on HTTPS or localhost (required for mic access)

### LLM model error
- Update `GROQ_MODEL` in `.env` or `config.py`
- Current working models: `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`

---

## 🐳 Docker Deployment

```bash
cp .env.example .env    # fill in
docker-compose up -d
```

---

## 📞 Deepgram TTS Voices

Popular English voices:
- `aura-2-thalia-en` — Friendly female
- `aura-2-luna-en` — Warm female  
- `aura-2-stella-en` — Professional female
- `aura-2-orion-en` — Clear male
- `aura-2-atlas-en` — Deep male

Change in `.env`: `DEEPGRAM_TTS_VOICE=aura-2-orion-en`
