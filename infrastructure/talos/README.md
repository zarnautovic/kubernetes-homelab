# Talos node rebuild procedure

What this directory alone can NOT rebuild: machine secrets, the full
machine configs, and the system-extension list are **not** in the repo.
Secrets and generated configs (`talosconfig`, `controlplane.yaml`) are
backed up on the management VM (`zlaya@192.168.1.199`).

## Cluster facts

| | |
|---|---|
| Talos | v1.13.3 (one Proxmox VM per HP EliteDesk G4 host) |
| Nodes | talos-icw-nam (192.168.1.143), talos-pv0-ntu (192.168.1.135), talos-node-hades (192.168.1.136) |
| API VIP | 192.168.1.100 (see `vip-patch.yaml`, interface ens18) |
| Longhorn disk | second disk `/dev/sdb`, mounted at `/var/mnt/longhorn` (see `patch-all.yaml`) |
| CNI | none at install — Cilium bootstrapped via Helm, then Flux-managed |
| kube-proxy | disabled (Cilium kube-proxy replacement, KubePrism `localhost:7445`) |

## System extensions and factory image

All three nodes run the same factory schematic (verified 2026-07-12 via
`talosctl get extensions`):

```
factory.talos.dev/installer/e37cea50363b49e1887745d13c0a9fcb282499ee982535f2369db3fa1ce770c1:v1.13.3
```

Extensions included in the schematic:

- `siderolabs/i915` — Intel iGPU firmware/driver (Plex HW transcode)
- `siderolabs/intel-ucode` — CPU microcode updates
- `siderolabs/qemu-guest-agent` — Proxmox guest integration
- `siderolabs/iscsi-tools` — required by Longhorn
- `siderolabs/util-linux-tools` — required by Longhorn

When upgrading Talos, keep the same schematic hash and change only the
version tag; regenerate the schematic at https://factory.talos.dev only
if the extension set itself changes.

## Rebuilding a dead node

1. Create the Proxmox VM: 16GB RAM, two disks (OS + dedicated Longhorn
   disk that will appear as `/dev/sdb`), NIC on the LAN bridge (ens18).
2. Boot the factory ISO (same extension set as above).
3. From the management VM (has `talosconfig` + `controlplane.yaml`):

   ```bash
   talosctl apply-config --insecure -n <new-node-ip> \
     -f controlplane.yaml \
     --config-patch @patch-all.yaml \
     --config-patch @vip-patch.yaml
   ```

4. The node joins etcd and the cluster (all three nodes are control
   plane). Longhorn detects the empty `/var/mnt/longhorn` disk and
   rebuilds replicas automatically.
5. If the dead node held Longhorn replicas, verify volume health in the
   Longhorn UI before doing anything else disruptive.

## Upgrades

```bash
talosctl upgrade --nodes <node-ip> --image <factory-image>:<new-version>
```

One node at a time; Longhorn's `node-drain-policy` is
`block-if-contains-last-replica`, so a drain waits if the node holds
the last healthy replica of any volume (this is intentional — do not
force it; wait for the rebuild).
