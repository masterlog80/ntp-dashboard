# NTP Dashboard

A Dockerized web dashboard for monitoring a local Chrony/NTP server or a remote NTP server over SSH. It provides live NTP source status, clock offset, GPS satellite/NMEA data, connected NTP clients, and optional host resource metrics in a lightweight browser UI.

The dashboard is designed for homelab and local NTP deployments, including GPS/PPS-backed NTP servers. It can run directly on the NTP host or on another machine and connect to the NTP host over SSH.

---

## Features

- 🕐 **NTP / Chrony status** – Current clock offset and Chrony source information
- 📡 **NTP source monitoring** – Source state, stratum, polling interval, reachability, last receive time, and samples
- 🛰️ **GPS satellite data** – Satellite visibility and GPS time when `gpspipe` is available on the target host
- 📍 **Remote GPS monitoring** – Collect GPS data from a remote NTP server over SSH
- 👥 **Connected NTP clients** – Show clients currently querying Chrony, including IP address, hit/drop counters, and last-seen information
- 💻 **Optional system monitoring** – CPU, memory, and thermal data from the configured host
- 🔐 **SSH password or private-key authentication** – Remote connections support either credentials or an SSH private key
- 🔒 **Encrypted credentials** – Stored SSH passwords and private keys are encrypted with a generated Fernet key
- 🎨 **Theme customization** – Light/dark UI with a browser-side colour picker; preferences are kept locally in the browser
- 📱 **Progressive Web App** – Includes a web app manifest and service worker
- 🔄 **Automatic refresh** – NTP source data refreshes every 2 seconds; GPS/satellite data refreshes every 30 seconds
- 🔐 **Optional HTTP authentication** – Protect the dashboard with HTTP Basic Authentication using environment variables
- 📦 **Optional GPS client support** – The container can be built with `gpsd-clients` when local `gpspipe` access is required
- 🏷️ **Version display** – The application version can be supplied at build/runtime and is displayed by the UI
- 🩺 **Container health check** – Docker checks the web UI on port `55234`

---

## Quick Start

### Prerequisites

| Requirement | Notes |
|---|---|
| Docker ≥ 20.10 | Docker Compose plugin recommended |
| Docker Compose ≥ 2.x | Required for the supplied `compose.yaml` |
| Chrony | Required on the NTP host being monitored |
| `/run/chrony` | Required for local deployments so the container can access Chrony's Unix socket |
| SSH access | Required only for Remote mode |
| `curl` and `jq` | `curl` is used by the shared build/deploy workflow; `jq` is optional |

For Debian/Ubuntu NTP hosts, Chrony can be installed with:

```bash
sudo apt update
sudo apt install chrony
```

### Clone & build

This repo's build/deploy logic uses the shared [`masterlog80/homelab-scripts`](https://github.com/masterlog80/homelab-scripts) workflow used by the other projects in this collection. Set the variables below and run it:

```bash
export REPO="masterlog80/ntp-dashboard"
export DIRNAME="ntp-dashboard"
export REGISTRY="zot.salvetti.info"
export IMAGE_NAME="ntp-dashboard"
export COMPOSE_FILE="compose.yaml"
export OPERATIONS=""

GH_TOKEN="${GH_TOKEN:-$GITHUB_TOKEN}"
[[ -z "$GH_TOKEN" ]] && read -s -p "GitHub token (required - homelab-scripts is private): " GH_TOKEN && echo
export GH_TOKEN

bash -c "$(curl -fsSL -H "Authorization: token ${GH_TOKEN}" https://raw.githubusercontent.com/masterlog80/homelab-scripts/main/clone-build.sh)"
```

The standard workflow builds the image from the repository and can deploy the supplied Compose configuration to the configured Docker host/registry environment.

### Run manually

If you prefer a normal Docker Compose deployment:

```bash
git clone https://github.com/masterlog80/ntp-dashboard.git
cd ntp-dashboard

docker compose up -d --build
```

The dashboard will be available at:

```text
http://<docker-host>:55234
```

For a protected deployment, set `DASHBOARD_AUTH_USER` and `DASHBOARD_AUTH_PASSWORD` in the container environment. Both must be set together.

### Uninstall

```bash
docker compose down

# Also remove the persisted dashboard configuration:
docker compose down -v
rm -rf ./data
```

> **Important:** The `data/` directory contains the encrypted SSH credentials/private key and the encryption key required to decrypt them. Back it up if you want to preserve the saved connection configuration.

---

## Deployment Modes

The dashboard supports two connection modes, selected from **Connection Setup** in the UI.

| Mode | Behaviour |
|---|---|
| 🏠 **Local** | Runs Chrony/GPS commands inside the container. Use this when the dashboard is deployed directly on the NTP server. |
| 🌐 **Remote** | Connects to another NTP server over SSH and runs the required Chrony/GPS commands there. |

### Local deployment

Local mode is intended for running the dashboard on the same host as Chrony.

The Compose deployment uses host networking and mounts `/run/chrony`:

```yaml
services:
  ntp-dashboard:
    build:
      context: .
      args:
        INSTALL_GPSD_CLIENTS: "false"
    container_name: ntp-dashboard
    network_mode: "host"
    environment:
      - LOG_LEVEL=INFO
    volumes:
      - ./data:/app/data
      - /run/chrony:/run/chrony
    restart: unless-stopped
```

`network_mode: "host"` is intentional for local deployments. It allows the container to communicate with Chrony on the host and makes the dashboard listen directly on host port `55234`.

### Remote deployment

Remote mode does not require the dashboard container to be on the NTP server. Enter the remote host, SSH username, and either an SSH password or private key in **Connection Setup**.

The application stores the connection configuration in `/app/data/config.json`. Passwords and private keys are encrypted using the Fernet key stored in `/app/data/secret.key`.

> **Security:** Protect the `data/` directory. Anyone who obtains both `config.json` and `secret.key` can decrypt the stored credentials.

---

## GPS Support

GPS monitoring is optional.

The default image intentionally does **not** install Alpine's `gpsd-clients` package. This keeps the standard image smaller and avoids installing GPS tooling when the dashboard is being used only to monitor a remote host.

If local GPS data is required, build the image with:

```bash
docker build \
  --build-arg INSTALL_GPSD_CLIENTS=true \
  -t ntp-dashboard:latest .
```

Or change the build argument in `compose.yaml`:

```yaml
build:
  context: .
  args:
    INSTALL_GPSD_CLIENTS: "true"
```

The application uses:

```bash
gpspipe -w -n 8
```

and parses `TPV` and `SKY` messages for GPS time and satellite information.

For Remote mode, GPS commands are executed on the configured SSH target, so the remote NTP server must provide the required GPS tooling itself.

> **Note:** A GPS receiver is not required for ordinary Chrony/NTP monitoring. GPS support is only needed when you want satellite and GPS-time information.

---

## Screenshots

### Dashboard
![NTP Dashboard](https://github.com/user-attachments/assets/8c26db82-3838-4c46-8c5a-135d765cc5ae)

### Connection Setup
![Connection Setup](https://github.com/user-attachments/assets/f33ea67f-cda3-49bb-850a-0d03c18ec7d4)

### SSH Key Authentication
![SSH Key Authentication](https://github.com/user-attachments/assets/7bd6cc08-7990-436a-374f-9e4cfba7dd2f)

### Theme Customization
![Theme customization](https://github.com/user-attachments/assets/1b2a41b7-d02c-4800-838f-9e4cfba7dd2f)

### Connected NTP Clients
![Connected NTP clients](https://github.com/user-attachments/assets/a870b1c2-ef97-4355-b312-be2144e512a6)

---

## Dashboard Data

### NTP Sources

The NTP section uses Chrony's `chronyc tracking` and `chronyc sources` output to display:

- Current system time offset
- Source state
- Source name/IP
- Stratum
- Poll interval
- Reachability
- Last receive time
- Last sample information

NTP data is refreshed every **2 seconds**.

### GPS / Satellites

When GPS support is available, the dashboard displays:

- GPS time
- Visible satellites
- Satellite status information returned by `gpspipe`

GPS data is refreshed every **30 seconds**.

### Connected Clients

The Clients view queries Chrony using `chronyc clients` and displays clients currently known to the NTP server.

For local deployments, the application tries several local `chronyc` invocation forms, including authenticated `-k` mode. For remote deployments, it uses SSH to execute the Chrony command on the target host.

If Chrony returns `501 not authorised`, configure the appropriate `cmdallow`/command authentication on the NTP host. The application reports this condition rather than treating an unauthorised response as a successful empty client list.

### System Metrics

The optional system monitor can report:

- CPU usage
- RAM used/total and percentage
- CPU/system temperature where the host exposes `/sys/class/thermal/thermal_zone0/temp`

Enable **Monitor** in the connection configuration before requesting these metrics.

---

## Docker Compose

The supplied `compose.yaml` is suitable for a local NTP-host deployment:

```yaml
services:
  ntp-dashboard:
    build:
      context: .
      args:
        INSTALL_GPSD_CLIENTS: "false"
    container_name: ntp-dashboard
    network_mode: "host"
    environment:
      - LOG_LEVEL=INFO
    volumes:
      - ./data:/app/data
      - /run/chrony:/run/chrony
    restart: unless-stopped
```

The application listens on **port `55234`**.

### Container health check

The image includes a Docker health check against the unauthenticated `/healthz` endpoint:

```text
http://127.0.0.1:55234/healthz
```

The check runs every 30 seconds, with a 10-second startup grace period and three retries.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `DEBUG_MODE` | unset | Set to `true` to explicitly enable Flask debug mode; do not use in production |
| `APP_VERSION` | `dev` | Version displayed by the application; normally supplied by the image/build workflow |
| `DASHBOARD_AUTH_USER` | unset | Username for HTTP Basic Authentication; enabled when both auth variables are set |
| `DASHBOARD_AUTH_PASSWORD` | unset | Password for HTTP Basic Authentication |
| `SSH_KNOWN_HOSTS` | `/app/data/known_hosts` | Trusted SSH host-key file used for strict remote host verification |

### Build arguments

| Argument | Default | Description |
|---|---|---|
| `INSTALL_GPSD_CLIENTS` | `false` | Set to `true` to install Alpine `gpsd-clients` for local `gpspipe` support |

The following paths are currently fixed by the application:

| Path | Purpose |
|---|---|
| `/app/data/config.json` | Persistent connection configuration |
| `/app/data/secret.key` | Fernet encryption key for saved credentials |
| `/run/chrony` | Chrony Unix socket directory mounted from the host in local mode |

---

## Persistent Configuration

Mount `/app/data` to preserve connection settings across container recreation:

```text
data/
├── config.json   # Connection mode, host/user and encrypted credentials
└── secret.key    # Fernet key used to encrypt/decrypt credentials
```

The SSH password and private key are encrypted before being written to `config.json`.

The encryption key is generated automatically on first use and is stored beside the configuration file. Do not delete or replace `secret.key` unless you also intend to discard the encrypted credentials and configure the connection again.

---

## Security Notes

- **Protect the dashboard:** HTTP Basic Authentication is available through `DASHBOARD_AUTH_USER` and `DASHBOARD_AUTH_PASSWORD`. For deployments exposed beyond a trusted LAN, enable it or place the dashboard behind an equivalent authentication/access-control layer.
- **Protect `data/`:** `config.json` contains encrypted credentials, while `secret.key` is required to decrypt them. The application creates the data directory as `0700` and these credential files as `0600`; also protect the host directory containing them.
- **SSH host keys:** Remote connections use strict host-key verification. Mount a trusted `known_hosts` file (default: `/app/data/known_hosts`, configurable with `SSH_KNOWN_HOSTS`) before using Remote mode. Unknown hosts are rejected rather than automatically trusted.
- **Remote command privileges:** Remote commands are executed using the configured SSH account. The connected account must have sufficient permissions to run the required Chrony/GPS commands. The Clients query may require Chrony command authorisation or `sudo` depending on the target configuration.
- **Debug mode:** Do not enable `DEBUG_MODE=true` on an exposed production deployment. Debug mode can expose detailed errors and tracebacks.
- **Host networking:** Local mode uses `network_mode: host`, which gives the container direct access to the host network namespace. This is required by the current local Chrony design.

---

## Troubleshooting

### Dashboard does not load

Check the container and logs:

```bash
docker compose ps
docker compose logs -f ntp-dashboard
```

Confirm that port `55234` is listening:

```bash
curl -v http://127.0.0.1:55234/
```

### Local NTP data is unavailable

Confirm Chrony is installed and running:

```bash
systemctl status chrony
chronyc tracking
chronyc sources
```

Then verify that the Chrony socket is available:

```bash
ls -la /run/chrony
```

The Compose deployment must mount `/run/chrony` into the container:

```yaml
volumes:
  - /run/chrony:/run/chrony
```

### GPS data is missing in Local mode

Check whether `gpspipe` is available in the container:

```bash
docker exec ntp-dashboard gpspipe --version
```

If it is missing, rebuild with:

```bash
docker compose build --build-arg INSTALL_GPSD_CLIENTS=true

docker compose up -d
```

Also confirm that the GPS receiver is available to the host and that `gpsd` is providing data.

### Remote connection fails

Verify SSH access independently:

```bash
ssh <user>@<ntp-host>
```

Then check the dashboard logs:

```bash
docker compose logs -f ntp-dashboard
```

Confirm that the SSH account can execute:

```bash
chronyc tracking
chronyc sources
```

and, when client monitoring is required:

```bash
chronyc clients
```

### Clients page reports `501 not authorised`

Chrony can restrict access to client information. Configure the target Chrony instance to allow the dashboard host/account to run the clients query, or configure Chrony command authentication as appropriate for your environment.

### Saved SSH credentials no longer work

Make sure both files still exist:

```bash
ls -la ./data/config.json ./data/secret.key
```

If `secret.key` was lost or replaced, the encrypted credentials can no longer be decrypted. Re-enter the SSH credentials in **Connection Setup** to generate a new encrypted value.

---

## API

The dashboard exposes the following read/write endpoints for its web UI:

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Dashboard UI |
| `GET` | `/api/ntp` | Chrony tracking and NTP source data |
| `GET` | `/api/gps` | GPS time and satellite data |
| `GET` | `/api/clients` | Connected NTP clients |
| `GET` | `/api/system_metrics` | Optional CPU, RAM, and temperature metrics |
| `GET` | `/api/config` | Current connection configuration with secrets redacted |
| `POST` | `/api/config` | Save connection configuration |
| `GET` | `/manifest.json` | PWA manifest |
| `GET` | `/sw.js` | PWA service worker |

The API is primarily intended for the bundled web interface rather than as a stable external API contract.

---

## Architecture

```text
                         ┌──────────────────────┐
 Browser                 │    NTP Dashboard      │
 ───────────────────────►│    Web UI / Flask    │
                         │      :55234           │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │   Connection Layer   │
                         │                      │
                         │  Local      Remote   │
                         └────┬──────────┬──────┘
                              │          │
                    ┌─────────▼───┐   ┌─▼──────────────┐
                    │ Local host  │   │ SSH NTP host   │
                    │             │   │                │
                    │ chronyc     │   │ chronyc        │
                    │ gpspipe     │   │ gpspipe        │
                    │ /run/chrony │   │ GPS receiver   │
                    └─────────────┘   └────────────────┘
```

The Flask application executes a small set of operating-system commands either locally or through Paramiko SSH, parses their output, and exposes the resulting data to the browser as JSON.

---

## Project Structure

```text
.
├── app.py                         # Flask application and API
├── compose.yaml                   # Docker Compose deployment
├── Dockerfile                     # Multi-stage Alpine image build
├── requirements.txt               # Python dependencies
├── templates/
│   ├── config.json                # Template placeholder
│   └── index.html                 # Dashboard UI
├── static/
│   ├── dashboard.js               # Dashboard frontend logic
│   ├── manifest.json              # PWA manifest
│   ├── sw.js                      # Service worker
│   └── images/
│       └── ntp-dashboard-logo.png
├── tests/
│   └── test_app.py                # Application tests
└── README.md
```

---

## Development

Create a Python virtual environment and install the application dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Run the application directly:

```bash
python app.py
```

The development server listens on:

```text
http://127.0.0.1:55234
```

Run the test suite with:

```bash
pip install pytest
python -m pytest tests -v
```

### Docker image smoke test

The repository's GitHub Actions workflow builds the image, reports its uncompressed size and starts a container on the host network to verify that the dashboard becomes reachable on port `55234`.

---

## Versioning

The application reads its version from the `APP_VERSION` environment variable, defaulting to `dev` when no version is supplied.

Git tags beginning with `v` are used by the release workflow to create GitHub Releases. For example:

```bash
git tag v1.0.0
git push origin v1.0.0
```

When publishing an image, supply the corresponding version as `APP_VERSION` so the UI can identify the deployed build.

---

## License

MIT License. See [`LICENSE`](./LICENSE).

---

## Disclaimer

This project is intended for monitoring and homelab use. It executes system commands and, in Remote mode, commands over SSH. Review the deployment, SSH permissions, network exposure, and stored credentials before using it on a production or untrusted network.
