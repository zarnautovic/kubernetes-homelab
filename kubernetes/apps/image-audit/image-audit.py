#!/usr/bin/env python3
"""Monthly image audit: running app images in the cluster vs. latest upstream release.

Runs the same way locally and in-cluster:
  local:      kubectl + (optional) gh for GitHub; prints the table
  in-cluster: pod list via the Kubernetes API (service account), GitHub/Docker Hub via plain HTTPS
If VIKUNJA_URL + VIKUNJA_TOKEN + VIKUNJA_TASK are set, posts the result as a comment on that task
(full table when at least one image has a newer upstream release, one short line otherwise).
Nothing is ever changed in the cluster or in git; this is read-only.
"""
import html, json, os, re, ssl, subprocess, sys, urllib.request

SKIP_PREFIXES = ("registry.k8s.io/", "quay.io/cilium/", "ghcr.io/fluxcd/", "ghcr.io/siderolabs/",
                 "docker.io/longhornio/csi-", "docker.io/longhornio/livenessprobe",
                 "docker.io/longhornio/longhorn-share-manager", "docker.io/longhornio/longhorn-instance-manager",
                 "docker.io/longhornio/longhorn-engine", "docker.io/longhornio/longhorn-ui",
                 "quay.io/jetstack/cert-manager-webhook", "quay.io/jetstack/cert-manager-cainjector",
                 "ghcr.io/immich-app/immich-machine-learning")
# image repo -> ("gh", "owner/repo"[, tag_regex]) GitHub releases, ("hub", "ns/repo", tag_regex) Docker Hub tags,
# ("manual", "note"). Own images (ghcr.io/zarnautovic/*) are git-sha tagged and deployed by hand.
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
    "python": ("hub", "library/python", r"^3\.13\.\d+-slim$"),
    "nousresearch/hermes-agent": ("hub", "nousresearch/hermes-agent", r"^v?\d+\.\d+\.\d+$"),
}
UA = {"User-Agent": "homelab-image-audit/1.0", "Accept": "application/json"}

def http_json(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    ctx = None
    cafile = os.environ.get("K8S_CA")
    if cafile and url.startswith(os.environ.get("K8S_API", "\0")):
        ctx = ssl.create_default_context(cafile=cafile)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.load(r)

def running_images():
    sa_token = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    if os.path.exists(sa_token):
        host, port = os.environ["KUBERNETES_SERVICE_HOST"], os.environ["KUBERNETES_SERVICE_PORT"]
        os.environ["K8S_API"] = f"https://{host}:{port}"
        os.environ["K8S_CA"] = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        pods = http_json(f"{os.environ['K8S_API']}/api/v1/pods?limit=1000",
                         {"Authorization": "Bearer " + open(sa_token).read()})
        images = [c["image"] for p in pods["items"] for c in p["spec"].get("containers", [])]
    else:
        out = subprocess.run("kubectl get pods -A -o json", shell=True, capture_output=True, text=True).stdout
        pods = json.loads(out)
        images = [c["image"] for p in pods["items"] for c in p["spec"].get("containers", [])]
    return sorted({i for i in images if not i.startswith(SKIP_PREFIXES)})

def split(image):
    ref = image.split("@")[0]
    if ":" in ref.rsplit("/", 1)[-1]:
        return ref.rsplit(":", 1)
    return ref, "latest"

def gh_api(path):
    headers = {}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        headers["Authorization"] = "Bearer " + tok
    try:
        return http_json("https://api.github.com/" + path, headers)
    except Exception as e:  # noqa
        return {"_error": e.__class__.__name__}

def vkey(tag):
    """Sort key: numeric components of a tag, so 1.21.2 > 1.20.4 regardless of release date."""
    return [int(x) for x in re.findall(r"\d+", tag)]

def latest_gh(repo, pattern=None):
    rels = gh_api(f"repos/{repo}/releases?per_page=30")
    if isinstance(rels, dict):
        return "? (" + rels.get("_error", rels.get("message", "api")) + ")"
    tags = [r["tag_name"] for r in rels if not r.get("prerelease") and not r.get("draft")]
    if pattern:
        tags = [t for t in tags if re.match(pattern, t)]
    if tags:
        return max(tags, key=vkey)
    t = gh_api(f"repos/{repo}/tags?per_page=1")
    return t[0]["name"] if isinstance(t, list) and t else "?"

def latest_hub(repo, pattern):
    try:
        data = http_json(f"https://hub.docker.com/v2/repositories/{repo}/tags?page_size=100&ordering=last_updated")
    except Exception as e:  # noqa
        return f"? ({e.__class__.__name__})"
    rx = re.compile(pattern)
    hits = [t["name"] for t in data["results"] if rx.match(t["name"])]
    return max(hits, key=vkey) if hits else "? (no tag matched)"

def norm(v):
    return re.sub(r"^(version/|v)", "", v).split("@")[0]

def audit():
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
        unknown = latest.startswith(("?", "("))
        newer = not unknown and norm(latest) != norm(tag) and not norm(tag).startswith(norm(latest))
        rows.append({"repo": repo, "running": tag, "latest": latest, "source": source, "newer": newer})
    return rows

def print_table(rows):
    w = max(len(r["repo"]) for r in rows)
    print(f"{'IMAGE':{w}}  {'RUNNING':28}  {'LATEST':28}  SOURCE")
    for r in rows:
        flag = "  <-- update?" if r["newer"] else ""
        print(f"{r['repo']:{w}}  {r['running'][:28]:28}  {r['latest'][:28]:28}  {r['source']}{flag}")

def post_comment(rows):
    url, token, task = os.environ.get("VIKUNJA_URL"), os.environ.get("VIKUNJA_TOKEN"), os.environ.get("VIKUNJA_TASK")
    if not (url and token and task) or token == "REPLACE_ME":
        print("Vikunja posting skipped (VIKUNJA_URL/TOKEN/TASK not set)")
        return
    from datetime import date
    newer = [r for r in rows if r["newer"]]
    if newer:
        body = [f"<p><strong>Audit slika {date.today():%d.%m.%Y}</strong>: {len(newer)} od {len(rows)} slika ima novije upstream izdanje.</p>",
                "<table><thead><tr><th>Slika</th><th>Sada</th><th>Upstream</th><th>Izvor</th></tr></thead><tbody>"]
        for r in newer:
            body.append(f"<tr><td><code>{html.escape(r['repo'])}</code></td><td>{html.escape(r['running'])}</td>"
                        f"<td><strong>{html.escape(r['latest'])}</strong></td><td>{html.escape(r['source'])}</td></tr>")
        body.append("</tbody></table>")
        unknown = [r for r in rows if r["latest"].startswith("?")]
        if unknown:
            body.append("<p>Bez odgovora/izvora: " + ", ".join(html.escape(r["repo"]) for r in unknown) + "</p>")
        comment = "".join(body)
    else:
        comment = f"<p>Audit slika {date.today():%d.%m.%Y}: sve {len(rows)} slike su na zadnjoj upstream verziji.</p>"
    req = urllib.request.Request(f"{url.rstrip('/')}/api/v1/tasks/{task}/comments", method="PUT",
                                 data=json.dumps({"comment": comment}).encode(),
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", **UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        print(f"posted comment to task {task} (HTTP {r.status})")

if __name__ == "__main__":
    rows = audit()
    print_table(rows)
    post_comment(rows)
