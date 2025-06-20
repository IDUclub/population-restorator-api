FROM python:3.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libpq-dev \
    libgeos-dev \
    git \
    curl && \
    pip install --no-cache-dir poetry && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md .env /app/

RUN poetry config virtualenvs.create false && \
    poetry install --no-root

COPY population-restorator-api-config.yaml /app/

COPY app /app/app

RUN chmod a+rwx /tmp && \
    mkdir -p /app/logs /app/calculation_dbs /app/working_db

RUN pip install .

CMD ["launch_population-restorator-api"]
