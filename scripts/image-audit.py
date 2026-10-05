#!/usr/bin/env python3
"""Monthly image audit: running app images in the cluster vs. latest upstream release.

Usage: scripts/image-audit.py            (needs kubectl, gh, network)
Prints a table IMAGE | RUNNING | LATEST | SOURCE. Review changelogs before bumping pins.
"""
import json, re, subprocess, sys, urllib.request

SKIP_PREFIXES = ("registry.k8s.io/", "quay.io/cilium/", "ghcr.io/fluxcd/", "ghcr.io/siderolabs/",
                 "docker.io/longhornio/csi-", "docker.io/longhornio/livenessprobe",
                 "docker.io/longhornio/longhorn-share-manager", "docker.io/longhornio/longhorn-instance-manager",
                 "docker.io/longhornio/longhorn-engine", "docker.io/longhornio/longhorn-ui",
                 "quay.io/jetstack/cert-manager-webhook", "quay.io/jetstack/cert-manager-cainjector",
                 "ghcr.io/immich-app/immich-machine-learning")
# image repo -> ("gh", "owner/repo") for GitHub releases, or ("hub", "ns/repo", tag_regex) for Docker Hub tags.
# Our own images (ghcr.io/zarnautovic/*) are git-sha tagged and deployed by hand, so they are listed without a lookup.
SOURCES = {
    "docker.io/longhornio/longhorn-manager": ("gh", "longhorn/longhorn"),
    "intel/intel-gpu-plugin": ("gh", "intel/intel-device-plugins-for-kubernetes"),
    "ghcr.io/recyclarr/recyclarr": ("gh", "recyclarr/recyclarr"),
    "ghcr.io/goauthentik/server": ("gh", "goauthentik/authentik"),
    "cloudflare/cloudflared": ("gh", "cloudflare/cloudflared"),
    "vikunja/vikunja": ("gh", "go-vikunja/vikunja"),
    "quay.io/jetstack/cert-manager-controller": ("gh", "cert-manager/cert-manager"),
    "ghcr.io/tautulli/tautulli": ("gh", "Tautulli/Tautulli"),
    "ghcr.io/stakater/reloader": ("gh", "stakater/Reloader", r"^v\d"),
    "ghcr.io/seerr-team/seerr": ("gh", "seerr-team/seerr"),
    "ghcr.io/immich-app/immich-server": ("gh", "immich-app/immich"),
    "ghcr.io/gethomepage/homepage": ("gh", "gethomepage/homepage"),
    "ghcr.io/flaresolverr/flaresolverr": ("gh", "FlareSolverr/FlareSolverr"),
    "ghcr.io/bookorbit/bookorbit": ("gh", "bookorbit/bookorbit"),
    "ghcr.io/autobrr/autobrr": ("gh", "autobrr/autobrr"),
    "ghcr.io/linuxserver/sonarr": ("gh", "linuxserver/docker-sonarr"),
    "ghcr.io/linuxserver/radarr": ("gh", "linuxserver/docker-radarr"),
    "ghcr.io/linuxserver/qbittorrent": ("gh", "linuxserver/docker-qbittorrent"),
    "ghcr.io/linuxserver/prowlarr": ("gh", "linuxserver/docker-prowlarr"),
    "ghcr.io/linuxserver/bazarr": ("gh", "linuxserver/docker-bazarr"),
    "adguard/adguardhome": ("gh", "AdguardTeam/AdGuardHome"),
    "plexinc/pms-docker": ("hub", "plexinc/pms-docker", r"^\d+\.\d+\.\d+\.\d+-[0-9a-f]+$"),
    "pgvector/pgvector": ("hub", "pgvector/pgvector", r"^\d+\.\d+\.\d+-pg18$"),
    "postgres": ("hub", "library/postgres", r"^18\.\d+-alpine$"),
    "docker.io/library/postgres": ("hub", "library/postgres", r"^17\.\d+-bookworm$"),
    "ghcr.io/immich-app/postgres": ("manual", "follow Immich release notes (vectorchord tag is dictated by Immich)"),
    "docker.io/valkey/valkey": ("hub", "valkey/valkey", r"^9\.1\.\d+-alpine$"),
    "couchdb": ("hub", "library/couchdb", r"^\d+\.\d+\.\d+(\.\d+)?$"),
    "python": ("hub", "library/python", r"^3\.13\.\d+-slim$"),  # floating 3.13-slim in use; shows the concrete patch
    "nousresearch/hermes-agent": ("hub", "nousresearch/hermes-agent", r"^v?\d+\.\d+\.\d+$"),
}

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout

def running_images():
    out = sh("kubectl get pods -A -o jsonpath='{range .items[*]}{range .spec.containers[*]}{.image}{\"\\n\"}{end}{end}'")
    imgs = set()
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith(SKIP_PREFIXES):
            continue
        imgs.add(line)
    return sorted(imgs)

def split(image):
    ref = image.split("@")[0]
    if ":" in ref.rsplit("/", 1)[-1]:
        repo, tag = ref.rsplit(":", 1)
    else:
        repo, tag = ref, "latest"
    return repo, tag

def latest_gh(repo, pattern=None):
    if pattern:
        out = sh(f"gh api 'repos/{repo}/releases?per_page=30' -q '.[]|select(.prerelease==false)|.tag_name' 2>/dev/null")
        hits = [t for t in out.split() if re.match(pattern, t)]
        return hits[0] if hits else "?"
    out = sh(f"gh api repos/{repo}/releases/latest -q .tag_name 2>/dev/null").strip()
    if not out:
        out = sh(f"gh api 'repos/{repo}/releases?per_page=5' -q '[.[]|select(.prerelease==false)][0].tag_name' 2>/dev/null").strip()
    if not out:
        out = sh(f"gh api 'repos/{repo}/tags?per_page=1' -q '.[0].name' 2>/dev/null").strip()
    return out or "?"

def latest_hub(repo, pattern):
    url = f"https://hub.docker.com/v2/repositories/{repo}/tags?page_size=100&ordering=last_updated"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            tags = [t["name"] for t in json.load(r)["results"]]
    except Exception as e:  # noqa
        return f"? ({e.__class__.__name__})"
    rx = re.compile(pattern)
    hits = [t for t in tags if rx.match(t)]
    return hits[0] if hits else "? (no tag matched)"

def norm(v):
    return re.sub(r"^(version/|v)", "", v).split("@")[0]

rows = []
for image in running_images():
    repo, tag = split(image)
    src = SOURCES.get(repo)
    if repo.startswith("ghcr.io/zarnautovic/"):
        latest, source = "(own build)", "git"
    elif not src:
        latest, source = "? (no source mapping)", "-"
    elif src[0] == "manual":
        latest, source = "(manual)", src[1]
    elif src[0] == "gh":
        latest, source = latest_gh(src[1], src[2] if len(src) > 2 else None), "gh:" + src[1]
    else:
        latest, source = latest_hub(src[1], src[2]), "hub:" + src[1]
    flag = "" if latest.startswith(("?", "(")) or norm(latest) == norm(tag) or norm(tag).startswith(norm(latest)) else "  <-- update?"
    rows.append((repo, tag, latest, source, flag))

w = max(len(r[0]) for r in rows)
print(f"{'IMAGE':{w}}  {'RUNNING':28}  {'LATEST':28}  SOURCE")
for repo, tag, latest, source, flag in rows:
    print(f"{repo:{w}}  {tag[:28]:28}  {latest[:28]:28}  {source}{flag}")
