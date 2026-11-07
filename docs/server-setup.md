# Server setup (staging and production)

Phase 5.6. Two servers on DigitalOcean, Bangalore (BLR1), Ubuntu 24.04 LTS:

| | Size | Domains (defaults) |
|---|---|---|
| **production** | 8 GB RAM / 4 vCPU (Basic, Premium Intel or AMD) | diagnose., admin., api., files.instantmechanic.online |
| **staging** | 4 GB RAM / 2 vCPU | diagnose.staging., admin.staging., api.staging., files.staging.instantmechanic.online |

instantmechanic.online itself (and www.) stays on the company's existing site: only the subdomains point here.

Everything below is done once per server, in this order. Production gets **its own, fresh** secrets: never copy
values from a laptop's `.env.prod` or from staging.

## 1. Create the droplet
- Image Ubuntu 24.04 (LTS) x64, region BLR1, the size above, **monitoring** on, **backups** off (the app's own
  encrypted backups are used: step 9), an IPv4 address (IPv6 optional).
- Authentication: **SSH key only**. Add your personal key (not the CI key).
- Optional but recommended: a DigitalOcean **Reserved IP**, so DNS survives a rebuild.

## 2. DNS
At the DNS provider of instantmechanic.online, add **A** records (TTL 300 while setting up) to the server's IP:

| Name | Production | Staging |
|---|---|---|
| diagnose | prod IP | — |
| admin | prod IP | — |
| api | prod IP | — |
| files | prod IP | — |
| diagnose.staging, admin.staging, api.staging, files.staging | — | staging IP |

Leave `@` and `www` as they are (the existing site). Add a **CAA** record `0 issue "letsencrypt.org"` (and
`0 issue "zerossl.com"`, Caddy's fallback) if the domain has none. Check: `dig +short api.instantmechanic.online`.

## 3. First login: a deploy user, SSH key only
As root (the only time):
```bash
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/ && chown deploy:deploy /home/deploy/.ssh/authorized_keys
echo 'deploy ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/deploy   # or set a password for sudo instead
```
Lock SSH down (`/etc/ssh/sshd_config.d/10-hardening.conf`):
```
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AllowUsers deploy
```
`systemctl reload ssh`, then **in a second terminal** check `ssh deploy@<ip>` works before closing the root session.

## 4. Firewall: 22, 80, 443 only
```bash
sudo ufw default deny incoming && sudo ufw default allow outgoing
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw allow 443/udp   # 443/udp: HTTP/3
sudo ufw enable && sudo ufw status
```
Docker publishes container ports by writing its own iptables rules, which bypass ufw. Only Caddy publishes ports in
docker-compose.prod.yml (80, 443), so nothing else is reachable; never add `ports:` to other services. Also add a
**DigitalOcean Cloud Firewall** with the same three rules as a second layer (it is outside the droplet, so Docker
cannot bypass it).

## 5. Swap and the basics
```bash
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swap.conf && sudo sysctl --system
sudo timedatectl set-timezone UTC          # logs and BACKUP_AT are in UTC
sudo apt-get update && sudo apt-get install -y ca-certificates curl rsync unattended-upgrades fail2ban
```
(Staging: 2G of swap is enough.)

## 6. Automatic security updates
```bash
sudo dpkg-reconfigure -plow unattended-upgrades      # answer Yes
```
In `/etc/apt/apt.conf.d/50unattended-upgrades` keep only the `-security` origins and set
`Unattended-Upgrade::Automatic-Reboot "true";` and `Unattended-Upgrade::Automatic-Reboot-Time "21:30";` (03:00 India
time, after the 02:30 backup). The containers come back by themselves (`restart: unless-stopped`).
`fail2ban` with its default `sshd` jail is enough.

## 7. Docker
Docker's own repository (not Ubuntu's `docker.io`):
```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker deploy      # log out and in again
```
Log rotation for anything not using the compose logging settings, `/etc/docker/daemon.json`:
```json
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "5" }, "live-restore": true }
```
then `sudo systemctl restart docker`.

## 8. The app's folders, settings and registry login
As `deploy`:
```bash
sudo install -d -o deploy -g deploy /opt/autocare /opt/autocare/releases /opt/autocare/shared \
  /opt/autocare/shared/backend /opt/autocare/shared/data /opt/autocare/shared/data/media
```
**Settings** (from the repo's `.env.prod.example` and `backend/.env.prod.example`; README "Phase 5.6" lists every value
and where it comes from). Write them with `nano`, never paste secrets into a chat or a ticket:
- `/opt/autocare/shared/.env.prod`: the domains (step 2), `CADDY_TLS=<ops email>`, `POSTGRES_PASSWORD`, the
  backup settings (step 9), the public build values are not needed here (CI bakes them into the images).
- `/opt/autocare/shared/backend/.env.prod`: the app's secrets.
- `chmod 600 /opt/autocare/shared/.env.prod /opt/autocare/shared/backend/.env.prod`
- `/opt/autocare/shared/deploy.env`:
  ```bash
  IMAGE_REPO=ghcr.io/yashiagarw       # ghcr.io/<GitHub owner, lower case>
  DEPLOY_ENVIRONMENT=production       # or staging
  COMPOSE_PROFILES=storage            # SeaweedFS for photos on this server
  PRE_DEPLOY_BACKUP=1                 # production: an encrypted backup before every deploy (staging: 0)
  ```

**Registry login (read-only)**. The images are private. On GitHub (the repo owner's account): Settings > Developer
settings > Personal access tokens > **Tokens (classic)** > Generate: note `ghcr-read <server>`, expiry 1 year (put
the date in the calendar), scope **read:packages only**. One token per server. Then on the server:
```bash
echo '<token>' | docker login ghcr.io -u yashiagarw --password-stdin     # stored in ~deploy/.docker/config.json
```
(GHCR does not accept fine-grained tokens for pulling packages; a classic token with only `read:packages` cannot
push, delete or read code.)

**The CI deploy key**: a separate key that only GitHub Actions uses:
```bash
ssh-keygen -t ed25519 -N '' -C "github-actions-<staging|production>" -f ./gha_<env>   # on your laptop
```
Append `gha_<env>.pub` to `/home/deploy/.ssh/authorized_keys` on that server (one line, optionally prefixed with
`from="<GitHub runner ranges>"` if you later use a static runner). The private key `gha_<env>` goes into the GitHub
environment secret `DEPLOY_SSH_KEY`, then delete it from the laptop. The server's host key line for
`DEPLOY_SSH_KNOWN_HOSTS`: `ssh-keyscan -t ed25519 <ip>` **run once you have checked the fingerprint**
(`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the server, compare).

## 9. Backups (the Phase 5.4 backup service)
Follow [runbooks/restore.md](runbooks/restore.md) "The key": a **new** age key for production (staging can have its
own or none). In `/opt/autocare/shared/.env.prod`: `BACKUP_AGE_RECIPIENT` (the public key), `BACKUP_REMOTE` and the
`BACKUP_S3_*` values of the off-site bucket (Cloudflare R2: a bucket per environment, a token limited to it, a 35-day
lifecycle rule). The `backup` service runs with every deploy; after the first deploy check:
```bash
docker logs autocare-prod-backup-1 | tail     # "next backup at ..."
docker exec autocare-prod-backup-1 backup.sh  # one now; then: ls in the bucket
```
and run the restore test once ([runbooks/restore.md](runbooks/restore.md)), recording it there.

## 10. First deploy and the data
1. In GitHub, add the environment's secrets and variables (README "Phase 5.6"), then push to `main` (or Actions >
   "Deploy (manual)" > deploy, with the latest main sha). The deploy ships the compose file, Caddy's config and
   `data/raw`, starts everything (migrations run first) and waits until it is healthy. Caddy gets the certificates
   on the first start (needs DNS from step 2).
2. Load the data once (about 10 minutes; the embedding model is in the image), on the server:
   ```bash
   cd /opt/autocare/releases/$(cat /opt/autocare/shared/current)
   dcp() { docker compose -p autocare-prod --project-directory . -f docker-compose.prod.yml --env-file /opt/autocare/shared/.env.prod "$@"; }
   export DATA_RAW_DIR=/opt/autocare/shared/data/raw DATA_MEDIA_DIR=/opt/autocare/shared/data/media
   . /opt/autocare/shared/deploy.env; sha=$(cat /opt/autocare/shared/current)
   export API_IMAGE=$IMAGE_REPO/autocare-api:$sha
   dcp --profile setup run --rm setup                      # photo bucket + vehicle catalogue (once)
   for c in "app.knowledge.importer --all" "app.knowledge.questions load --all" "app.knowledge.merges apply" \
            "app.knowledge.requirements apply" "app.knowledge.phrases load" "app.knowledge.safety_triggers apply" \
            "app.vision.catalogue seed" "app.knowledge.embeddings sync" "app.parts build"; do
     dcp --profile tools run --rm tools python -m $c || break
   done
   ```
   Then publish the version once on the admin Datasets page, and create the super admin
   (README "Create your super admin").
3. Smoke test from your laptop: `sh scripts/deploy/smoke.sh diagnose.instantmechanic.online api.instantmechanic.online admin.instantmechanic.online`.

## Afterwards
- Uptime monitor: [runbooks/uptime.md](runbooks/uptime.md). Sentry: README "Phase 5.4".
- `ssh deploy@<server> 'sh /opt/autocare/releases/$(cat /opt/autocare/shared/current)/scripts/deploy/remote-deploy.sh status'`
  shows what runs.
- Monthly: `sudo apt-get dist-upgrade` in a quiet hour, the restore test, `df -h` (Docker images: the deploy script
  prunes unused ones older than 14 days).
