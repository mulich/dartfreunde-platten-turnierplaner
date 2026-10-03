FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TOURNAMENT_DB=/data/tournaments.sqlite3
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home dart && mkdir /data && chown dart:dart /data
COPY dartabend ./dartabend
USER dart
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["uvicorn", "dartabend.main:app", "--host", "0.0.0.0", "--port", "8000"]
