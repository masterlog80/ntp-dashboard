# syntax=docker/dockerfile:1

FROM python:3.13.14-alpine3.23 AS builder

LABEL org.opencontainers.image.title="NTP Dashboard" \
      org.opencontainers.image.description="A UI to check the status of NTP server" \
      org.opencontainers.image.source="https://github.com/masterlog80/ntp-dashboard" \
      org.opencontainers.image.url="https://github.com/masterlog80/ntp-dashboard" \
      org.opencontainers.image.documentation="https://github.com/masterlog80/ntp-dashboard" \
      org.opencontainers.image.authors="Lorenzo (via Github Copilot/Claude)" \
      org.opencontainers.image.vendor="Lorenzo (via Github Copilot/Claude)" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="0.2" \
      org.opencontainers.image.created="2026-09-17T08:00:00Z"

WORKDIR /build

# Build Python dependencies in a throw-away stage so compilers and headers
# are not included in the final runtime image.
RUN apk add --no-cache \
    build-base \
    libffi-dev \
    openssl-dev \
    python3-dev

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade "pip==26.1.2" \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# Tailwind's Play CDN is kept local for the current UI, but generated only in
# the build stage so wget and its build-time dependencies are not retained.
RUN mkdir -p /build/static \
    && wget -q https://cdn.tailwindcss.com/ -O /build/static/tailwindcss.js

FROM python:3.13.14-alpine3.23

WORKDIR /app

ARG INSTALL_GPSD_CLIENTS=false

# Runtime-only packages. Keep package versions aligned with the Alpine 3.23
# repositories used by the pinned Python base image. Avoid apk upgrade here:
# mixing a full upgrade with pinned packages can make builds fail when the
# repository moves to a newer security revision.
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

# Install only the already-built Python dependencies from the builder.
COPY --from=builder /install /usr/local

# Copy only files required at runtime. Tests, CI configuration, documentation,
# and other repository-only files are excluded from the image.
COPY app.py ./
COPY templates ./templates
COPY static ./static
COPY --from=builder /build/static/tailwindcss.js ./static/tailwindcss.js

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 55234

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:55234/', timeout=3)" || exit 1

CMD ["python", "app.py"]
