# Talos node rebuild procedure

What this directory alone can NOT rebuild: machine secrets and the full
machine config are **not** in the repo (it is public). They are kept
age-encrypted outside git — see [Machine secrets backup](#machine-secrets-backup).

## Cluster facts

| | |
|---|---|
| Talos | v1.14.2 (one Proxmox VM per HP EliteDesk G4 host) |
| Nodes | talos-icw-nam (192.168.1.143), talos-pv0-ntu (192.168.1.135), talos-node-hades (192.168.1.136) |
| API VIP | 192.168.1.100 (see `vip-patch.yaml`, interface ens18) |
| Longhorn disk | second disk `/dev/sdb`, mounted at `/var/mnt/longhorn` (see `patch-all.yaml`) |
| CNI | none at install — Cilium bootstrapped via Helm, then Flux-managed |
| kube-proxy | disabled (Cilium kube-proxy replacement, KubePrism `localhost:7445`) |

## System extensions and factory image

All three nodes run the same factory schematic (verified 2026-09-24 via
`talosctl get extensions`; upgraded to v1.14.2 on 2026-10-02):

```
factory.talos.dev/installer/e37cea50363b49e1887745d13c0a9fcb282499ee982535f2369db3fa1ce770c1:v1.14.2
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
3. From the management VM, decrypt the live config
   ([backup](#machine-secrets-backup)) and apply it as is:

   ```bash
   age -d -i ~/.config/sops/age/keys.txt ~/talos-secrets/controlplane.yaml.age > controlplane.yaml
   talosctl apply-config --insecure -n <new-node-ip> -f controlplane.yaml
   shred -u controlplane.yaml
   ```

   This is the merged live config: `patch-all.yaml` and `vip-patch.yaml`
   are already in it. Do **not** pass them again — Talos appends list
   entries on merge, so re-patching duplicates nameservers, time servers,
   mounts etc. If the backup config is unusable, regenerate one from the
   secrets bundle (fresh install only):

   ```bash
   age -d -i ~/.config/sops/age/keys.txt ~/talos-secrets/secrets.yaml.age > secrets.yaml
   talosctl gen config homelab https://192.168.1.143:6443 \
     --with-secrets secrets.yaml --install-image <factory-installer-above> \
     --config-patch @patch-all.yaml --config-patch @vip-patch.yaml \
     --output-types controlplane -o controlplane.yaml
   shred -u secrets.yaml
   ```

   **If the dead node is 192.168.1.143:** the config's
   `cluster.controlPlane.endpoint` is `https://192.168.1.143:6443`, so a
   new node would try to join through the node that is gone. Before
   `apply-config`, point it at a live member or the VIP
   (`https://192.168.1.100:6443`, needs etcd up). Running nodes don't care
   — kubelets use KubePrism (`localhost:7445`); kubeconfigs use the VIP and
   talosconfig lists all three nodes as endpoints (set 2026-10-06).

4. The node joins etcd and the cluster (all three nodes are control
   plane). Longhorn detects the empty `/var/mnt/longhorn` disk and
   rebuilds replicas automatically.
5. If the dead node held Longhorn replicas, verify volume health in the
   Longhorn UI before doing anything else disruptive.
6. **Talos >= 1.14 fresh installs mount EPHEMERAL (`/var`) with `noexec`**
   (upgraded nodes keep the old `rw` mount - verified on all three on
   2026-10-02 via `talosctl read /proc/mounts`). Longhorn v1 executes engine
   binaries from `/var/lib/longhorn/engine-binaries`, so on a rebuilt node
   check `talosctl -n <ip> read /proc/mounts | grep ' /var '` first. If it
   shows `noexec`, apply a `VolumeConfig` for `EPHEMERAL` with
   `mount.secure: false` (see Talos 1.14 release notes and
   longhorn/longhorn#14097) before letting Longhorn schedule replicas there.

## Upgrades

```bash
talosctl upgrade --nodes <node-ip> --image <factory-image>:<new-version>
```

One node at a time (last done 2026-10-02: 1.14.1 -> 1.14.2, order .143,
.135, .136), after a manual etcd snapshot (`etcd-snapshot.sh`, see below).
Afterwards sync
`machine.install.image` on every node:

```bash
talosctl -n <node-ip> patch mc -p @infrastructure/talos/install-image-patch.yaml
```

Longhorn's `node-drain-policy` is
`block-if-contains-last-replica`, so a drain waits if the node holds
the last healthy replica of any volume (this is intentional — do not
force it; wait for the rebuild).

## Machine secrets backup

Not in git (this repo is public). age-encrypted to the same recipient as
SOPS (`.sops.yaml`), so the existing key decrypts them:

| File | Content |
|---|---|
| `controlplane.yaml.age` | full live machine config — identical on all three nodes, patches already merged |
| `secrets.yaml.age` | `talosctl gen secrets` bundle: Talos/Kubernetes/etcd CAs, SA key, tokens, secretbox key |

- **Where:** `~/talos-secrets/` on the management VM (canonical, in the
  Proxmox vzdump) and `~/backups/talos/` on the laptop. Created
  2026-10-06 from the live nodes; decryption, `talosctl validate -m metal`
  of the config and the CA/cluster-id/secretbox match against all three
  nodes verified.
- **Decrypt:** `age -d -i ~/.config/sops/age/keys.txt secrets.yaml.age > secrets.yaml`
  — work in a temp dir and `shred -u` the plaintext afterwards.
- **Redo after** a CA rotation (`talosctl rotate-ca`) or any machine config
  change. The live config is
  `talosctl -n <ip> get machineconfig v1alpha1 -o jsonpath='{.spec}'` (two
  documents: `v1alpha1` + `HostnameConfig`). Always name the `v1alpha1`
  resource: there is an identical `persistent` one, and an unnamed `get`
  concatenates both into a file that `apply-config` rejects.
  `talosctl gen secrets --from-controlplane-config` accepts only the
  `v1alpha1` document — strip `HostnameConfig` first, and send its stderr
  to `/dev/null`: on a parse error it prints the whole config, secrets
  included.
- With `secrets.yaml` a lost or expired admin `talosconfig` can be
  regenerated: `talosctl gen config ... --with-secrets secrets.yaml
  --output-types talosconfig`.

## etcd snapshot and restore

Snapshots are manual on purpose (no cron, decision 2026-08-05): workload
data is covered by Longhorn backups, the cluster itself is rebuildable.
Take one before risky work (Talos/Kubernetes upgrades, node replacement,
large Longhorn snapshot purges):

```bash
infrastructure/talos/etcd-snapshot.sh            # snapshot from 192.168.1.143
infrastructure/talos/etcd-snapshot.sh 192.168.1.135   # or from another member
```

- **Where:** `~/etcd-snapshots/` on the management VM (.199) is the
  canonical copy; the script keeps the newest 5. The management VM is in
  the Proxmox vzdump, so the snapshots are backed up with it. Copies on a
  workstation (e.g. `~/backups/talos/`) are extras, not the reference.
- **Size:** the DB was 53 MB (21 MB in use) on 2026-10-05; a file under
  1 MB is rejected by the script.

### Restore or not?

| Situation | Action |
|---|---|
| One control-plane node dead, the other two healthy (quorum intact) | **Do not restore.** Remove the dead member (`talosctl -n <healthy-ip> etcd members`, then `talosctl -n <healthy-ip> etcd remove-member <id>`) and rebuild the node ("Rebuilding a dead node"); it rejoins and syncs. |
| Two or three members lost, or etcd data corrupted (quorum gone) | Restore from snapshot (below). |
| Kubernetes objects deleted by mistake | Usually Flux re-applies them from git. A restore rolls the **whole** cluster state back to snapshot time — last resort only. |

### Restore procedure (quorum lost)

Follows the Talos "Disaster Recovery" guide. Longhorn data lives on the
separate `/dev/sdb` disk (`/var/mnt/longhorn`, see `patch-all.yaml`),
which none of these steps touch.

1. **Pick the snapshot:** newest `~/etcd-snapshots/etcd-*.db`. If there is
   no snapshot but one member's data directory is still readable, copy the
   raw DB instead: `talosctl -n <ip> cp /var/lib/etcd/member/snap/db ./db`
   (needs `--recover-skip-hash-check` in step 4).
2. **Stop etcd everywhere.** On each control-plane node
   `talosctl -n <ip> service etcd` must show `Preparing` (waiting for
   bootstrap). A node that still has old etcd data gets only its
   EPHEMERAL partition wiped (machine config and the Longhorn disk stay):

   ```bash
   talosctl -n <ip> reset --graceful=false --reboot --system-labels-to-wipe=EPHEMERAL
   ```

3. Wait until **all three** nodes report etcd `Preparing`.
4. **Bootstrap one node from the snapshot:**

   ```bash
   talosctl -n 192.168.1.143 bootstrap --recover-from=./etcd-YYYYMMDD-HHMMSS.db
   # raw DB copy from step 1: add --recover-skip-hash-check
   ```

5. The other two nodes join on their own. Verify:

   ```bash
   talosctl -n 192.168.1.143 etcd members                                   # 3 members
   talosctl -n 192.168.1.143,192.168.1.135,192.168.1.136 etcd status
   kubectl get nodes
   kubectl get pods -A | grep -v -E 'Running|Completed'
   ```

6. **Nodes whose EPHEMERAL was wiped:** check
   `talosctl -n <ip> read /proc/mounts | grep ' /var '`. A re-created
   EPHEMERAL on Talos >= 1.14 may come back `noexec`, which breaks Longhorn
   engine binaries; fix it as in step 6 of "Rebuilding a dead node"
   before Longhorn volumes attach there.
7. Cluster objects are now at snapshot time. Bring manifests back to git
   HEAD with `flux reconcile source git flux-system && flux reconcile
   kustomization flux-system`, then confirm all Longhorn volumes are
   Healthy before anything else disruptive.
