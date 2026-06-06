# Homelab

GitOps repository for my homelab Kubernetes cluster.

## Stack

| Component | Technology |
|---|---|
| OS | Talos Linux v1.13.3 |
| Kubernetes | v1.35.5 |
| CNI | Cilium v1.19.4 (kube-proxy replacement, native routing, Gateway API, L2 announcements) |
| GitOps | Flux CD v2.8 |
| Secrets | SOPS + age |
| Storage | Longhorn v1.12.0 + TrueNAS NFS |

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

Traffic flow for external access:

```
Internet → Router (443) → Ubuntu VM (Traefik) → Kubernetes LB (192.168.1.240) → Cilium Gateway API
```

- Gateway API v1.2.1 with Cilium GatewayClass
- Gateway `main` in `network` namespace — listeners on HTTP :80 and HTTPS :443
- HTTP → HTTPS redirect at gateway level
- Cilium is bootstrapped via Helm at install (CNI chicken-and-egg) and managed day-2 by a Flux HelmRelease (`kube-system/cilium`)

## Repository Structure

```
kubernetes/
├── flux/               # Flux Kustomization resources (one per app)
└── apps/
    ├── cert-manager/   # TLS certificate management
    ├── gateway-api/    # Gateway + HTTPRoutes
    ├── kube-system/    # Cilium (HelmRelease), metrics-server, reloader
    ├── longhorn-system/# Distributed block storage + NFS backups
    ├── authentik/      # SSO / identity provider
    ├── homepage/       # Dashboard
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
    └── obsidian-livesync/ # CouchDB backend for Obsidian LiveSync
```

> URLs below use `example.com` as a placeholder for the real domain.

## Applications

### Infrastructure

| App | Namespace | URL | Notes |
|---|---|---|---|
| Cilium | kube-system | — | CNI, kube-proxy replacement, Gateway API, L2; Flux-managed HelmRelease |
| cert-manager | cert-manager | — | DNS-01 via Cloudflare, letsencrypt staging + production |
| Longhorn | longhorn-system | longhorn.example.com | Distributed block storage (×3 replicas), daily NFS backups, auto engine-upgrade |
| Authentik | authentik | authentik.example.com | SSO / identity provider, embedded outpost |
| Homepage | homepage | example.com | Dashboard with Proxmox, TrueNAS, Authentik, Plex widgets |
| Obsidian LiveSync | obsidian-livesync | obsidian-sync.example.com | CouchDB sync backend for Obsidian |

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

## Storage

Three distinct tiers:

- **Longhorn v1.12.0** — replicated (×3) block storage for app config/database PVCs. Data lives on each node's dedicated disk at `/var/mnt/longhorn` (`/dev/sdb`). Volume engines auto-upgrade to the chart's default image (`concurrentAutomaticEngineUpgradePerNodeLimit: 1`), so they never drift behind the Longhorn version.
- **Longhorn backups** — daily snapshots pushed **off-cluster** to TrueNAS NFS.
  - Target: `nfs://192.168.1.101:/mnt/backup-pool/backup` (NFSv3, nolock)
  - Recurring job `backup-critical` (group `default`): all volumes, daily 02:00, retain 7
- **TrueNAS NFS (media)** — bulk media + downloads, mounted by the media stack.
  - `nfs://192.168.1.101:/mnt/main-pool/media`
  - PVs use `storageClassName: ""`, RWX, Retain policy, pre-bound via `claimRef`

## Secrets

Secrets are encrypted with SOPS + age and committed to the repository. The `.sops.yaml` config encrypts `data`/`stringData` fields in all `kubernetes/**/*.yaml` files.

```bash
# Encrypt a secret
sops -e -i kubernetes/apps/<app>/secret.yaml

# Edit an encrypted secret
sops kubernetes/apps/<app>/secret.yaml
```
