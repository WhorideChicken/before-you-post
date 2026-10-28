FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.11.32

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY app ./app
COPY static ./static

# The host sets PORT (Render: 10000). MODEL_API_KEY (standard mode) and OPEN_API_KEY (private mode) come from the
# host's secret env vars; with neither, only the recorded samples run.
EXPOSE 7860
CMD ["sh", "-c", ".venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
