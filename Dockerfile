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

# Runtime-only packages. Build tools and development headers stay in the
# builder stage, substantially reducing the final image footprint.
RUN set -eux; \
    apk upgrade --no-cache; \
    apk add --no-cache chrony; \
    apk add --no-cache \
        musl \
        gnutls=3.8.13-r0 \
        p11-kit=0.26.2-r0 \
        expat=2.8.2-r0 \
        libffi \
        libcrypto3=3.5.7-r0 \
        libssl3=3.5.7-r0

# Install only the already-built Python dependencies from the builder.
COPY --from=builder /install /usr/local

# Copy only files required at runtime. Tests, CI configuration, documentation,
# and other repository-only files are excluded from the image.
COPY app.py ./
COPY templates ./templates
COPY static ./static
COPY --from=builder /build/static/tailwindcss.js ./static/tailwindcss.js

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

EXPOSE 55234

CMD ["python", "app.py"]
