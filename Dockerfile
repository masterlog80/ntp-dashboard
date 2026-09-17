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

RUN mkdir -p /build/static \
    && wget -q https://cdn.tailwindcss.com/ -O /build/static/tailwindcss.js

FROM python:3.13.14-alpine3.23

WORKDIR /app

ARG INSTALL_GPSD_CLIENTS=false
ARG APP_VERSION=latest

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
        apk add --no-cache gpsd-clients; \
    fi

COPY --from=builder /install /usr/local

# Runtime metadata: keep the build-time image version available without
# requiring Docker socket access or Kubernetes API access. The build workflow
# can override APP_VERSION for versioned images; local/default images use
# "latest", matching the normal Docker tag used for this image.
RUN printf '%s\n' "$APP_VERSION" > /app/.version

# Install the runtime hooks into Python's site-packages. The .pth file is
# processed by Python before app.py is imported, so this works even when
# Docker/Kubernetes explicitly starts `python app.py` and bypasses run.py.
COPY ntp_dashboard_runtime.py /usr/local/lib/python3.13/site-packages/
COPY ntp_dashboard_favicon.py /usr/local/lib/python3.13/site-packages/
COPY ntp_dashboard_runtime.pth /usr/local/lib/python3.13/site-packages/

COPY app.py ./
COPY server.py ./
COPY run.py ./
COPY sitecustomize.py ./
COPY templates ./templates
COPY static ./static
COPY --from=builder /build/static/tailwindcss.js ./static/tailwindcss.js

ENV APP_VERSION=${APP_VERSION} \
    IMAGE_NAME=ntp-dashboard \
    IMAGE_VERSION=${APP_VERSION} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.title="NTP Dashboard" \
      org.opencontainers.image.description="A UI to check the status of NTP server" \
      org.opencontainers.image.source="https://github.com/masterlog80/ntp-dashboard" \
      org.opencontainers.image.url="https://github.com/masterlog80/ntp-dashboard" \
      org.opencontainers.image.documentation="https://github.com/masterlog80/ntp-dashboard" \
      org.opencontainers.image.authors="Lorenzo (via Github Copilot/Claude)" \
      org.opencontainers.image.vendor="Lorenzo (via Github Copilot/Claude)" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${APP_VERSION}"

EXPOSE 55234

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:55234/', timeout=3)" || exit 1

CMD ["python", "run.py"]
