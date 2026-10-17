FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Docker CLI only (no daemon): used for `docker ps/logs/restart` when the socket is mounted.
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker

RUN useradd --system --uid 10001 --no-create-home aiops \
 && mkdir -p /data && chown aiops /data
COPY aiops_agent ./aiops_agent
COPY config.yaml .

ENV AIOPS_DATA_DIR=/data
USER aiops
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -m aiops_agent.main -c /app/config.yaml healthcheck
CMD ["python", "-m", "aiops_agent.main", "-c", "/app/config.yaml", "run"]
