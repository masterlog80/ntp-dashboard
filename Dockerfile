# syntax=docker/dockerfile:1

FROM python:3.13.14-alpine3.23 AS builder

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

# Runtime-only packages. Build tools and development headers stay in the
# builder stage, substantially reducing the final image footprint.
RUN set -eux; \
    apk upgrade --no-cache; \
    apk add --no-cache \
        chrony \
        gnutls=3.8.13-r0 \
        p11-kit=0.26.2-r0 \
        expat=2.8.2-r0 \
        libffi \
        libcrypto3=3.5.7-r0 \
        libssl3=3.5.7-r0; \
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
