# Novel Proofreader

Local/private web app for Thai novel proofreading, folder batch review, glossary consistency checks, and file management.

## Run With Docker Compose

Create `.env` from `.env.example`, then set `GOOGLE_API_KEY`, `AUTH_USERNAME`, and `AUTH_PASSWORD`.

```bash
docker compose up -d --build
```

Open:

```text
http://SERVER_IP:8010/
```

## DigitalOcean Droplet Quick Deploy

On Ubuntu 24.04:

```bash
apt update
apt install -y git ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo ${UBUNTU_CODENAME:-$VERSION_CODENAME}) stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Clone your private repo:

```bash
mkdir -p /opt
cd /opt
git clone https://github.com/JessadaKung/Novel-Proofreader.git novel-proofreader
cd novel-proofreader
cp .env.example .env
nano .env
docker compose up -d --build
```

## Multiple Stories

Use `docker-compose.multi.example.yml` as a template. Each story should map a different host port, for example:

- `8010:8010`
- `8011:8010`
- `8012:8010`

Each story can have its own folders and `.env`.

## Security

Do not commit `.env`.

Set these before exposing the app:

```env
AUTH_USERNAME=admin
AUTH_PASSWORD=use-a-long-random-password
```

The app includes a File Manager, so public deployments must be password protected.
