#!/usr/bin/env bash
# Manual etcd snapshot — disaster recovery for losing etcd quorum.
#
# Run by hand before risky cluster work (Talos/Kubernetes upgrades, node
# replacement, heavy Longhorn snapshot purges). There is deliberately no
# cron: workload data is covered by Longhorn backups, and the cluster
# itself can be rebuilt (decision 2026-08-05).
#
# Usage:  infrastructure/talos/etcd-snapshot.sh [node-ip]
# Runs wherever a working talosconfig exists (management VM .199 is the
# canonical place; its home directory is included in the Proxmox vzdump).
# Restore procedure: README.md in this directory, "etcd snapshot and restore".
set -euo pipefail

NODE="${1:-192.168.1.143}"
DIR="${ETCD_SNAPSHOT_DIR:-$HOME/etcd-snapshots}"
KEEP="${ETCD_SNAPSHOT_KEEP:-5}"

mkdir -p "$DIR"
chmod 700 "$DIR"

echo "== etcd status (snapshot is taken from $NODE)"
talosctl -n 192.168.1.143,192.168.1.135,192.168.1.136 etcd status

out="$DIR/etcd-$(date +%Y%m%d-%H%M%S).db"
talosctl -n "$NODE" etcd snapshot "$out"
chmod 600 "$out"

# A healthy snapshot is tens of MB; a tiny file means something went wrong.
size=$(stat -c %s "$out")
if [ "$size" -lt 1000000 ]; then
  echo "ERROR: $out is only $size bytes — not a usable snapshot" >&2
  exit 1
fi

# Rotation by count, not age: snapshots are rare and manual, so an age
# limit could delete the only good one. Keep the newest $KEEP.
ls -1t "$DIR"/etcd-*.db | tail -n +"$((KEEP + 1))" | xargs -r rm -v --

echo "== OK: $out ($((size / 1024 / 1024)) MB)"
ls -lh "$DIR"
