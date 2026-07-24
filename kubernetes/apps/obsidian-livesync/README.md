# Obsidian LiveSync + LiveSync Bridge

Two workloads in this namespace:

- **couchdb** — the Self-hosted LiveSync remote vault (CouchDB) used by
  Obsidian on all devices.
- **livesync-bridge** — [vrtmrz/livesync-bridge](https://github.com/vrtmrz/livesync-bridge),
  a headless replicator that mirrors the vault two-way to plain files on
  TrueNAS NFS (`/mnt/main-pool/vault-mirror`, synced into `vault/`), so
  Home Assistant and automation agents can read/write notes without
  Obsidian.

## Bridge image

No upstream image is published; ours is built from source:

```
ghcr.io/zarnautovic/livesync-bridge:<upstream short sha>
```

To rebuild (e.g. after a plugin upgrade changes the database format):

```bash
git clone --recursive https://github.com/vrtmrz/livesync-bridge
cd livesync-bridge
docker build -t ghcr.io/zarnautovic/livesync-bridge:$(git rev-parse --short HEAD) .
docker push ghcr.io/zarnautovic/livesync-bridge:$(git rev-parse --short HEAD)
```

Then bump the tag in `bridge-deployment.yaml`. Keep the bridge and the
Obsidian plugin roughly in step — they share `livesync-commonlib`, and a
plugin-side database format change is the realistic breakage vector.

## Bridge configuration

`bridge-secret.yaml` holds `config.json` (SOPS-encrypted): the CouchDB
peer (same credentials as `couchdb-credentials`, plus the vault's E2EE
passphrase from the plugin's Remote Database settings) and the storage
peer writing to `data/vault/` (the NFS mount). Edit with:

```bash
sops kubernetes/apps/obsidian-livesync/bridge-secret.yaml
```

`useRemoteTweaks: true` makes the bridge adopt chunk-size settings from
the remote, so they don't need to be kept in sync manually.

## Caveats

- **Two-way sync**: deletions and edits in the mirror propagate back to
  the vault on every device. Point automation at it deliberately.
- **NFS watch limitation**: the bridge's file watcher only sees writes
  made through its own mount. Files written to the NFS export by *other*
  machines may not sync until the pod restarts (`scanOfflineChanges`
  picks them up at startup). Vault → file direction is always live.
- The container runs as the `deno` user (uid **1993** in the official
  Deno image); the TrueNAS dataset must allow uid 1993 to write.
- First run after a config change can be started with `--reset` (edit
  the deployment args temporarily) to rescan everything from scratch.

## Home Assistant

Mount the mirror in HA via Settings → System → Storage → Add network
storage: server `192.168.1.101`, NFSv4/v3, remote share
`/mnt/main-pool/vault-mirror`. Notes appear under the chosen usage
folder (e.g. `/media/vault/...`) for template/file sensors and scripts.
