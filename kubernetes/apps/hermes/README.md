# Hermes Agent

[Hermes Agent](https://hermes-agent.nousresearch.com/) (Nous Research) —
autonomous agent with persistent memory, skills, and a messaging
gateway. Runs here in gateway mode with **Telegram** as the chat surface
and **OpenAI Codex (ChatGPT-subscription OAuth)** as the model provider
— no API key, authenticated via device-code flow.

All state (config, OAuth credentials, memories, skills, sessions) lives
on the `hermes-data` Longhorn PVC at `/opt/data`. The Obsidian vault
mirror is mounted read-only at `/vault` (uid 10000 can read the
1993-owned dataset via world-read).

## First-time setup

1. **Telegram bot**: message @BotFather → `/newbot` → copy the token.
   Message @userinfobot → copy your numeric user ID.
2. **Fill the secret** (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`):

   ```bash
   sops kubernetes/apps/hermes/secret.yaml
   ```

3. After Flux applies and the pod starts, **authenticate ChatGPT OAuth**
   (device-code flow — open the printed URL in any browser, enter the
   code):

   ```bash
   kubectl exec -it -n hermes deploy/hermes -- \
     hermes auth add openai-codex --type oauth --no-browser
   kubectl exec -it -n hermes deploy/hermes -- hermes model
   kubectl rollout restart -n hermes deploy/hermes
   ```

## Security posture

- Gateway is default-deny; only `TELEGRAM_ALLOWED_USERS` may talk to it.
  Never set `GATEWAY_ALLOW_ALL_USERS`.
- Terminal backend is `local` — agent commands run *inside this pod*
  (non-root uid 10000, resource-limited, no cluster RBAC). Keep the
  "smart" dangerous-command approval mode on.
- The OpenAI-compatible API (8642) is cluster-internal only. The web
  dashboard (9119) is off; if enabled later it must sit behind
  Authentik (OIDC) — auth is mandatory on non-loopback binds.
- `auth.json` on the PVC holds the ChatGPT OAuth tokens — treat the
  volume as secret material (it is covered by Longhorn NFS backups).

## Upgrades

Bump the pinned image tag in `deployment.yaml`; schema migrations run
automatically on start. Data on the PVC survives recreation.
