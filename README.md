# Homelab

GitOps repository for my homelab Kubernetes cluster.

## Stack

| Component | Technology |
|---|---|
| OS | Talos Linux v1.14.2 |
| Kubernetes | v1.36.5 |
| CNI | Cilium v1.20.2 (kube-proxy replacement, native routing, Gateway API, L2 announcements) |
| GitOps | Flux CD v2.9 |
| Secrets | SOPS + age |
| Storage | Longhorn v1.12.1 + TrueNAS NFS |

## Nodes

Each Talos node is a Proxmox VM (16GB RAM allocated), one per physical **HP EliteDesk G4 Mini** host (32GB RAM each). All three are control-plane nodes with scheduling enabled (hyperconverged).

| Node | Host | IP | VM RAM |
|---|---|---|---|
| talos-icw-nam | zeus | 192.168.1.143 | 16GB |
| talos-pv0-ntu | poseidon | 192.168.1.135 | 16GB |
| talos-node-hades | hades | 192.168.1.136 | 16GB |

- **API VIP**: 192.168.1.100
- **LB IP pool**: 192.168.1.240/28 (Cilium L2 announcements)

## Networking

Two Cilium Gateways in the `network` namespace share one wildcard certificate (`*.example.com`, cert-manager DNS-01 via Cloudflare):

```
Public:  Internet → Cloudflare (proxied) → Cloudflare Tunnel (cloudflared) → Gateway `public` (192.168.1.243) → app
Private: LAN / Tailscale → Gateway `main` (192.168.1.240) → app
```

- No inbound port forwarding: the tunnel is outbound-only; `cloudflared` sends `*.example.com` to the `cilium-gateway-public` service.
- A route's `parentRef` decides its exposure. Only routes on `public` are reachable from the internet; everything on `main` (admin UIs behind the Authentik proxy, Vikunja, Hermes) is LAN/Tailscale-only.
- external-dns (Cloudflare, source `gateway-httproute`, policy `sync`) writes the records: proxied CNAMEs to the tunnel for `public` routes (target annotation on the Gateway), A records to 192.168.1.240 for `main` routes — they resolve everywhere but only answer on the LAN or over Tailscale.
- Gateway API v1.6.1 with Cilium GatewayClass
- HTTP → HTTPS redirect at gateway level (`main`)
- Cilium is bootstrapped via Helm at install (CNI chicken-and-egg) and managed day-2 by a Flux HelmRelease (`kube-system/cilium`)

## Repository Structure

```
docs/                   # AdGuard config reference, Longhorn backup morning check
scripts/image-audit.py  # local wrapper for the daily image audit (see kubernetes/apps/image-audit)
kubernetes/
├── flux/               # Flux Kustomization resources (one per app)
└── apps/
    ├── cert-manager/   # TLS certificate management
    ├── gateway-api/    # Gateways main (private) + public (tunnel), wildcard cert, HTTP→HTTPS redirect
    ├── cloudflared/    # Cloudflare Tunnel → Gateway public
    ├── external-dns/   # Cloudflare DNS records from HTTPRoutes
    ├── kube-system/    # Cilium (HelmRelease), metrics-server, reloader
    ├── longhorn-system/# Distributed block storage + NFS backups
    ├── authentik/      # SSO / identity provider
    ├── homepage/       # Dashboard
    ├── adguard/        # AdGuard Home — LAN DNS (ad blocking, .home names), LB 192.168.1.244
    ├── qbittorrent/    # Torrent client (VPN)
    ├── prowlarr/       # Indexer manager + FlareSolverr
    ├── autobrr/        # IRC/RSS release automation
    ├── sonarr/         # TV show management
    ├── radarr/         # Movie management
    ├── bazarr/         # Subtitle management
    ├── recyclarr/      # TRaSH Guides quality-profile sync (CronJob)
    ├── seerr/          # Media request management
    ├── plex/           # Media server
    ├── tautulli/       # Plex analytics
    ├── intel-gpu-plugin/ # iGPU device plugin
    ├── obsidian-livesync/ # CouchDB backend for Obsidian LiveSync + livesync-bridge file mirror
    ├── hermes/         # Hermes Agent (Telegram gateway, ChatGPT OAuth)
    ├── health-api/     # Apple Health import + vault index + stats API/dashboard (Go)
    ├── immich/         # Photo/video backup (server, ML, Valkey, Postgres+VectorChord)
    ├── bookorbit/      # Ebook library + KOReader/Kobo sync (app + Postgres/pgvector)
    ├── vikunja/        # Task/project tracker for the homelab (app + Postgres), built-in MCP server
    └── image-audit/    # Daily CronJob: running images vs upstream releases (own builds vs upstream commits), table in the Vikunja audit task
```

> URLs below use `example.com` as a placeholder for the real domain.

## Applications

### Infrastructure

| App | Namespace | URL | Notes |
|---|---|---|---|
| Cilium | kube-system | — | CNI, kube-proxy replacement, Gateway API, L2; Flux-managed HelmRelease |
| cert-manager | cert-manager | — | DNS-01 via Cloudflare, letsencrypt staging + production |
| Gateway API | network | — | Gateways `main` (192.168.1.240, private) and `public` (192.168.1.243, behind the tunnel); wildcard TLS |
| cloudflared | cloudflared | — | Cloudflare Tunnel (2 replicas, outbound-only) → Gateway `public`; no port forwarding |
| external-dns | external-dns | — | Cloudflare records from HTTPRoutes: proxied CNAME to the tunnel for `public`, A → 192.168.1.240 for `main` |
| Longhorn | longhorn-system | longhorn.example.com | Distributed block storage (×3 replicas), daily NFS backups, auto engine-upgrade |
| Authentik | authentik | authentik.example.com | SSO / identity provider, embedded outpost |
| Homepage | homepage | home.example.com | Dashboard with Proxmox, TrueNAS, Authentik, Plex widgets; private (Gateway `main`) |
| AdGuard Home | adguard | adguard.example.com | LAN DNS on LB 192.168.1.244 (UDP/TCP 53, externalTrafficPolicy Local); router DHCP hands out `.244,.1` so the router stays the fallback when the rack is down; `.home` names forwarded to the router, static hosts via DNS rewrites; config lives on the PVC (UI), not in git |
| Obsidian LiveSync | obsidian-livesync | obsidian-sync.example.com | CouchDB sync backend for Obsidian |
| LiveSync Bridge | obsidian-livesync | — | Two-way mirror of the vault to TrueNAS NFS plain files (for Home Assistant + agents); image built from source at ghcr.io/zarnautovic/livesync-bridge |
| Hermes Agent | hermes | — | Autonomous agent (Nous Research); Telegram chat surface, ChatGPT-subscription OAuth (Codex), vault mirror mounted read-only; web dashboard private (Gateway `main`), login via Authentik OIDC |
| health-api | health-api | health.example.com | Go service: Apple Health (HAE) and Strong imports, SQLite index of the vault's Health notes, stats/calibration/program API + dashboard; behind the Authentik proxy; image built by GitHub Actions |
| Immich | immich | photos.example.com | Photo/video backup; official OCI chart (server + ML + Valkey) + own Postgres/VectorChord StatefulSet on Longhorn; library on TrueNAS NFS; LAN endpoint 192.168.1.242:2283 for phone uploads (bypasses Cloudflare's 100 MB body limit) |
| BookOrbit | bookorbit | books.example.com | Ebook library (Calibre library on TrueNAS NFS `main-pool/books`), web reader, OPDS, KOReader/Kobo sync; own Postgres/pgvector StatefulSet on Longhorn; login via Authentik OIDC |
| Vikunja | vikunja | tasks.example.com | Task/project tracker for homelab work (Kanban/list/Gantt, CalDAV); own Postgres StatefulSet on Longhorn; private (Gateway `main`, LAN + Tailscale); built-in MCP server at `/api/v2/mcp` used by Claude Code with a scoped API token; login via Authentik OIDC only (local login disabled) |
| image-audit | image-audit | — | Daily CronJob: running images vs upstream releases (livesync-bridge: commits behind upstream main) → table in the Vikunja audit task; comments only when the candidate set changes |

### Media Stack

| App | Namespace | URL | Notes |
|---|---|---|---|
| qBittorrent | qbittorrent | qbittorrent.example.com | Gluetun sidecar (NordVPN WireGuard), VueTorrent UI |
| Prowlarr | prowlarr | prowlarr.example.com | Indexer manager, FlareSolverr sidecar |
| autobrr | autobrr | autobrr.example.com | IRC/RSS release automation, feeds the download client |
| Sonarr | sonarr | sonarr.example.com | TV show automation, External auth |
| Radarr | radarr | radarr.example.com | Movie automation, External auth |
| Bazarr | bazarr | bazarr.example.com | Subtitle automation |
| Recyclarr | recyclarr | — | CronJob syncing TRaSH Guides quality profiles to Sonarr/Radarr |
| Seerr | seerr | seerr.example.com | Media request UI, connects to Plex + Sonarr + Radarr |
| Plex | plex | plex.example.com | Media server, LB IP 192.168.1.241:32400, Intel UHD 630 HW transcode |
| Tautulli | tautulli | tautulli.example.com | Plex analytics and monitoring |
| Intel GPU plugin | kube-system | — | Device plugin exposing the iGPU (`gpu.intel.com/i915`) for Plex HW transcode |

## Storage

Three distinct tiers:

- **Longhorn v1.12.1** — replicated (×3) block storage for app config/database PVCs. Data lives on each node's dedicated disk at `/var/mnt/longhorn` (`/dev/sdb`). Volume engines auto-upgrade to the chart's default image (`concurrentAutomaticEngineUpgradePerNodeLimit: 1`), so they never drift behind the Longhorn version.
- **Longhorn backups** — daily snapshots pushed **off-cluster** to TrueNAS NFS.
  - Target: `nfs://192.168.1.101:/mnt/backup-pool/backup` (NFSv3, nolock)
  - Volumes are split into three staggered groups (`nightly-a`/`b`/`c`, balanced by size, assigned via `recurring-job-group.longhorn.io/<group>` labels on the Longhorn Volume CRs) so snapshot purge/coalescing never hits every volume at once. Unlabelled volumes fall into `default`, which the group-c jobs also sweep, so new PVCs are always backed up.
  - Layered recurring jobs (all times UTC, deliberately after the 02:00 UTC Proxmox vzdump window on the same ZFS pool): `backup-daily-{a,b,c}` Mon–Sat 04:00/05:00/06:00 retain 7, `backup-weekly-{a,b,c}` Sun 04:00/05:00/06:00 retain 8, `backup-monthly-{a,b,c}` 1st 08:00/09:00/10:00 retain 6 — restore points from yesterday back to ~6 months. `backupConcurrentLimit: 1` keeps the I/O burst survivable.
- **TrueNAS NFS (media)** — bulk media + downloads, mounted by the media stack.
  - `nfs://192.168.1.101:/mnt/main-pool/media`
  - PVs use `storageClassName: ""`, RWX, Retain policy, pre-bound via `claimRef`
- **TrueNAS NFS (photos)** — Immich library (originals, thumbnails, encoded video, Immich DB dumps), runs as UID/GID 3001.
  - `nfs://192.168.1.101:/mnt/main-pool/photos` (share limited to the three node IPs, 500 GiB quota)
  - ZFS snapshots hourly (48 h) / daily (30 d) / monthly (12 mo), replicated nightly to `backup-pool/photos`
- **TrueNAS NFS (vault mirror)** — plain-file mirror of the Obsidian vault, written by livesync-bridge and mounted read-mostly by Home Assistant and automation.
  - `nfs://192.168.1.101:/mnt/main-pool/vault-mirror`

## Secrets

Secrets are encrypted with SOPS + age and committed to the repository. The `.sops.yaml` config encrypts `data`/`stringData` fields in all `kubernetes/**/*.yaml` files.

```bash
# Encrypt a secret
sops -e -i kubernetes/apps/<app>/secret.yaml

# Edit an encrypted secret
sops kubernetes/apps/<app>/secret.yaml
```
