#!/bin/sh
set -eu

if [ "${ENABLE_GPSD:-false}" = "true" ]; then
    GPS_DEVICE="${GPS_DEVICE:-/dev/ttyACM0}"
    GPSD_SOCKET="${GPSD_SOCKET:-/var/run/gpsd.sock}"

    if [ ! -e "$GPS_DEVICE" ]; then
        echo "ERROR: ENABLE_GPSD=true but GPS_DEVICE does not exist: $GPS_DEVICE" >&2
        exit 1
    fi

    if ! command -v gpsd >/dev/null 2>&1; then
        echo "ERROR: ENABLE_GPSD=true but gpsd is not installed. Rebuild with INSTALL_GPSD_CLIENTS=true." >&2
        exit 1
    fi

    mkdir -p "$(dirname "$GPSD_SOCKET")"
    rm -f "$GPSD_SOCKET"
    echo "Starting gpsd on $GPS_DEVICE (socket: $GPSD_SOCKET)"
    gpsd -N -G -F "$GPSD_SOCKET" "$GPS_DEVICE" &
    GPSD_PID=$!

    "$@" &
    APP_PID=$!

    cleanup() {
        kill "$APP_PID" 2>/dev/null || true
        kill "$GPSD_PID" 2>/dev/null || true
    }
    trap cleanup INT TERM EXIT

    wait "$APP_PID"
    STATUS=$?
    trap - INT TERM EXIT
    kill "$GPSD_PID" 2>/dev/null || true
    wait "$GPSD_PID" 2>/dev/null || true
    exit "$STATUS"
fi

exec "$@"