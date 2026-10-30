# SMDPIS backend — FastAPI + scikit-learn
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: psycopg2-binary ships wheels, build-essential is a safety net.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Pre-fetch NLTK resources so first analysis never blocks on the network.
RUN python -c "import nltk; [nltk.download(r, quiet=True) for r in ('vader_lexicon','stopwords','wordnet','omw-1.4','punkt')]"

COPY backend/ /app/backend/
COPY ml/ /app/ml/
COPY scripts/ /app/scripts/
COPY data/sample/ /app/data/sample/

WORKDIR /app/backend

# Non-root user
RUN useradd --create-home --shell /bin/bash smdpis \
    && mkdir -p /app/data /app/backend/models \
    && chown -R smdpis:smdpis /app
USER smdpis

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
