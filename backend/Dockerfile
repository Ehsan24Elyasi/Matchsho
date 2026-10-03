ARG PYTHON_IMAGE=python:3.11-alpine@sha256:f2cdc43fcddbabe870f53750cbdcc01ae4aa75b1959351252457fde88f91d20f
FROM ${PYTHON_IMAGE} AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.lock .
RUN pip install --prefix=/install --require-hashes -r requirements.lock

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN addgroup -g 10001 app && adduser -D -u 10001 -G app app \
    && python -m pip uninstall -y pip setuptools wheel
WORKDIR /app
COPY --from=builder /install /usr/local
COPY --chown=app:app . .
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-access-log"]
