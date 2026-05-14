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

USER agent

# Pre-download VAD model at build time as agent user (avoids cold-start delay)
RUN python -c "from livekit.plugins import silero; silero.VAD.load()"

ENTRYPOINT ["/usr/bin/tini", "--"]
# -u: unbuffered stdout/stderr so logs appear immediately in docker logs
CMD ["python", "-u", "agent.py", "start"]
