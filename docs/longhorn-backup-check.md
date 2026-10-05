# Noćna backup oluja — što provjeriti ujutro (od 2026-08-05)

## Kontekst (incident 2026-08-04)

Proxmox vzdump (02:00 UTC = 04:00 lokalno) i Longhorn backup su se poklapali
na istom ZFS poolu (QLC NVMe mirror) → disk stall → Longhorn replike padaju
na i/o timeout → rebuild oluja → etcd ne stigne fsync-ati WAL → 40+ raft
elekcija (02:55–03:08) → sve leader-elected komponente (scheduler,
controller-manager, cilium-operator, flux, cert-manager, CSI) gube lease i
restartaju se.

## Primijenjeni fixevi

- **Proxmox**: Longhorn data diskovi (500G, zvol `zd80`) isključeni iz
  vzdump-a (`backup=0`) na sva tri VM-a — vzdump sad čita samo 64G system diskove
- **Longhorn** (commiti `948dc8c`, `1f70926` u kubernetes-homelab): backupi u
  3 grupe iza vzdump prozora:
  - `nightly-a` 04:00 UTC — plex, health-api, autobrr
  - `nightly-b` 05:00 UTC — prowlarr, hermes, sonarr
  - `nightly-c` + `default` 06:00 UTC — radarr, authentik-pg, qbittorrent,
    tautulli, seerr, bazarr, couchdb (default hvata i buduće PVC-ove)
  - monthly 08:00, 1. u mjesecu
- Otprije (commit `e245b6d`): engineReplicaTimeout=30 (max),
  backupConcurrentLimit=1, concurrency=1, iscsid noop_out 10s/30s

## Jutarnja provjera (kriterij: sve nule)

```bash
# 1. Nijedan novi restart preko noći na leader-elected komponentama
kubectl get pods -A | awk '$5+0 > 0' | grep -E "scheduler|controller-manager|cilium-operator|flux|cert-manager|csi-"
# → restarti smiju biti samo oni stari (5h+ prije, tj. od 04.08.)

# 2. Nijedna nova etcd raft elekcija nakon 2026-08-04
talosctl --nodes 192.168.1.135 logs etcd 2>&1 | grep "starting a new election" | tail -5

# 3. Backupi svih 13 volumena prošli u novim terminima (04/05/06 UTC)
kubectl get backups.longhorn.io -n longhorn-system \
  --sort-by=.metadata.creationTimestamp \
  -o custom-columns=VOL:.status.volumeName,STATE:.status.state,CREATED:.metadata.creationTimestamp | tail -15

# 4. Nema failanih replika / rebuilda tijekom noći
kubectl logs -n longhorn-system -l app=longhorn-manager --since=12h 2>/dev/null | grep -ciE "FailedSnapshotPurge|Cleaning up corrupted"

# 5. (Proxmox UI) vzdump log: traje kratko i piše "backup=disabled" za 500G disk
```

Ako 1–4 prođu čisto par noći zaredom → incident zatvoren, fajl se može obrisati.
