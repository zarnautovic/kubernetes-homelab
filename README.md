# Homelab

GitOps repository for my homelab Kubernetes cluster.

## Stack

| Component | Technology |
|---|---|
| OS | Talos Linux v1.12.4 |
| Kubernetes | v1.35.0 |
| CNI | Cilium v1.18.7 |
| GitOps | Flux CD v2.8.0 |
| Secrets | SOPS + age |
| Storage | Longhorn + TrueNAS NFS |

## Nodes

Each Talos node is a Proxmox VM (16GB RAM allocated), one per physical **HP EliteDesk G4 Mini** host (32GB RAM each).

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

## Repository Structure

```
kubernetes/
├── flux/               # Flux Kustomization resources (one per app)
└── apps/
    ├── cert-manager/   # TLS certificate management
    ├── gateway-api/    # Gateway + HTTPRoutes
    ├── kube-system/    # Cilium, metrics-server, reloader
    ├── longhorn-system/# Distributed block storage
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

## Applications

### Infrastructure

| App | Namespace | URL | Notes |
|---|---|---|---|
| cert-manager | cert-manager | — | DNS-01 via Cloudflare, letsencrypt staging + production |
| Longhorn | longhorn-system | longhorn.zlaya.tech | Distributed block storage, nodeDrainPolicy: always-allow |
| Authentik | authentik | authentik.zlaya.tech | SSO / identity provider, embedded outpost |
| Homepage | homepage | zlaya.tech | Dashboard with Proxmox, TrueNAS, Authentik, Plex widgets |
| Obsidian LiveSync | obsidian-livesync | obsidian-sync.zlaya.tech | CouchDB sync backend for Obsidian |

### Media Stack

| App | Namespace | URL | Notes |
|---|---|---|---|
| qBittorrent | qbittorrent | qbittorrent.zlaya.tech | Gluetun sidecar (NordVPN WireGuard), VueTorrent UI |
| Prowlarr | prowlarr | prowlarr.zlaya.tech | Indexer manager, FlareSolverr sidecar |
| autobrr | autobrr | autobrr.zlaya.tech | IRC/RSS release automation, feeds the download client |
| Sonarr | sonarr | sonarr.zlaya.tech | TV show automation, External auth |
| Radarr | radarr | radarr.zlaya.tech | Movie automation, External auth |
| Bazarr | bazarr | bazarr.zlaya.tech | Subtitle automation |
| Recyclarr | recyclarr | — | CronJob syncing TRaSH Guides quality profiles to Sonarr/Radarr |
| Seerr | seerr | seerr.zlaya.tech | Media request UI, connects to Plex + Sonarr + Radarr |
| Plex | plex | plex.zlaya.tech | Media server, LB IP 192.168.1.241:32400, Intel UHD 630 HW transcode |
| Tautulli | tautulli | tautulli.zlaya.tech | Plex analytics and monitoring |

## Storage

- **Longhorn**: replicated block storage for app config PVCs
- **TrueNAS NFS**: 3TB share for all media and downloads
  - NFS PVs use `storageClassName: ""`, RWX, Retain policy, pre-bound via `claimRef`

## Secrets

Secrets are encrypted with SOPS + age and committed to the repository. The `.sops.yaml` config encrypts `data`/`stringData` fields in all `kubernetes/**/*.yaml` files.

```bash
# Encrypt a secret
sops -e -i kubernetes/apps/<app>/secret.yaml

# Edit an encrypted secret
sops kubernetes/apps/<app>/secret.yaml
```
