FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Seoul OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 energy
COPY --chown=energy:energy . .
RUN mkdir -p /app/runtime-data && chown energy:energy /app/runtime-data
USER energy
ENV ENERGY_HISTORY_DB=/app/runtime-data/history.sqlite3
HEALTHCHECK --interval=30s --timeout=12s --start-period=45s --retries=3 CMD ["python","deploy/healthcheck.py"]
CMD ["python","deploy/entrypoint.py"]
