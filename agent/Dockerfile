FROM python:3.11-slim

# tini: proper PID-1 signal handling (SIGTERM forwarding, zombie reaping)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    gcc \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user with home dir (needed for model cache)
RUN useradd -r -m -s /bin/false agent

COPY --chown=agent:agent . .

# WORKDIR created /app as root before `agent` existed -- COPY --chown above only
# covers the files it copied in, not the /app directory entry itself, so the
# agent user could read/list here but not create new files (e.g. the
# failed_reports.jsonl fallback in agent.py silently failing with EACCES the
# moment a report POST to the backend fails). Chown the directory itself too.
RUN chown agent:agent /app

USER agent

# Pre-download VAD model at build time as agent user (avoids cold-start delay)
RUN python -c "from livekit.plugins import silero; silero.VAD.load()"

# Pre-download turn-detector model at build time (avoids a runtime crash on first
# call — the model files aren't bundled and error out if not already cached)
RUN python -m livekit.agents download-files

ENTRYPOINT ["/usr/bin/tini", "--"]
# -u: unbuffered stdout/stderr so logs appear immediately in docker logs
CMD ["python", "-u", "agent.py", "start"]
