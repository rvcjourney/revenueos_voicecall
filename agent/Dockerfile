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

# WORKDIR created /app as root before `agent` existed above -- chown it now so
# the agent user can create new files here later (e.g. the failed_reports.jsonl
# fallback in agent.py, which would otherwise silently fail with EACCES the
# moment a report POST to the backend fails). Doing this before COPY means
# COPY --chown below only has to cover the files it adds, not the directory
# entry itself.
RUN chown agent:agent /app

USER agent

# Pre-download plugin model files (noise cancellation) now, while this layer only
# depends on requirements.txt above -- NOT on the app code copied in below -- so
# a code-only change doesn't force a re-download on every deploy.
RUN python -m livekit.agents download-files

COPY --chown=agent:agent . .

ENTRYPOINT ["/usr/bin/tini", "--"]
# -u: unbuffered stdout/stderr so logs appear immediately in docker logs
CMD ["python", "-u", "agent.py", "start"]
