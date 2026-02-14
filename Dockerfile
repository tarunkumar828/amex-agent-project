FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY src /app/src
COPY pyproject.toml /app/pyproject.toml

ENV PYTHONPATH=/app/src

CMD ["python", "-m", "uca_orchestrator.api"]

