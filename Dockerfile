# syntax=docker/dockerfile:1

FROM python:3.13.14-alpine3.23 AS builder

WORKDIR /build

RUN apk add --no-cache \
    build-base \
    libffi-dev \
    openssl-dev \
    python3-dev

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade "pip==26.1.2" \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13.14-alpine3.23

WORKDIR /app

ARG INSTALL_GPSD_CLIENTS=true

RUN set -eux; \
    apk add --no-cache \
        chrony \
        gnutls \
        p11-kit \
        expat \
        libffi \
        libcrypto3 \
        libssl3; \
    if [ "$INSTALL_GPSD_CLIENTS" = "true" ]; then \
        apk add --no-cache gpsd gpsd-clients; \
    fi

COPY --from=builder /install /usr/local

COPY ntp_dashboard_runtime.py /usr/local/lib/python3.13/site-packages/
COPY ntp_dashboard_favicon.py /usr/local/lib/python3.13/site-packages/
COPY ntp_dashboard_runtime.pth /usr/local/lib/python3.13/site-packages/

COPY app.py ./
COPY server.py ./
COPY run.py ./
COPY sitecustomize.py ./
COPY docker-entrypoint.sh ./
COPY templates ./templates
COPY static ./static

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.title="NTP Dashboard" \
      org.opencontainers.image.description="A UI to check the status of NTP server" \
      org.opencontainers.image.source="https://github.com/masterlog80/ntp-dashboard" \
      org.opencontainers.image.url="https://github.com/masterlog80/ntp-dashboard" \
      org.opencontainers.image.documentation="https://github.com/masterlog80/ntp-dashboard" \
      org.opencontainers.image.authors="Lorenzo (via Github Copilot/Claude)" \
      org.opencontainers.image.vendor="Lorenzo (via Github Copilot/Claude)" \
      org.opencontainers.image.licenses="MIT"

EXPOSE 55234

# Use Alpine's wget for the health probe so the check does not pay Python startup/import cost.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:55234/healthz || exit 1

ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]
CMD ["python", "run.py"]
