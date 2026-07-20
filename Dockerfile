# ─────────────────────────────────────────────────────────────
# Indicator AI Assistant — API Server
# ─────────────────────────────────────────────────────────────
# Stage 1: Builder — install deps into a clean venv
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# ─────────────────────────────────────────────────────────────
# Stage 2: Runtime — lean final image
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy the pre-built virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source only — knowledge_base/ is intentionally
# NOT copied. It's only read by build_index.py (an offline script,
# confirmed via code search to never run inside the app/ package
# at request time). vector_store.index + chunk_metadata.pkl below
# already contain everything derived from it.
COPY app/ ./app/

# Copy pre-built FAISS index and chunk metadata
# (built with `python build_index.py` — MUST exist before building
# this image; the container does not build them itself)
COPY vector_store.index  ./vector_store.index
COPY chunk_metadata.pkl  ./chunk_metadata.pkl

# FastEmbed writes model files here (matches cache_dir="./model_cache"
# in app/embedding/embedder.py, and the model_cache volume mount in
# docker-compose.yml) — pre-create so it exists before first write.
RUN mkdir -p model_cache

# ── Environment ────────────────────────────────────────────
# All secrets must be passed at runtime via --env-file or -e flags.
# Do NOT bake secrets into the image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose the API port
EXPOSE 8000

# ── Healthcheck ─────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# ── Entrypoint ───────────────────────────────────────────────
# Single worker — each worker independently loads its own copy of
# the embedding model (measured ~200-365MB) plus the FAISS index at
# startup. Running more than one worker multiplies that memory cost
# per worker; it is not a data-safety requirement, purely a memory one.
CMD ["uvicorn", "app.api.server:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info"]