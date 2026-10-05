# AdGuard Home u k8s — plan (2.10.2026)

**STATUS 2.10.2026 (popodne): koraci 1–4 GOTOVI** (commit 9a94b05). Pod radi (hades), DNS na 192.168.1.244 odgovara (UDP+TCP), rewriteovi + `.home` prosljeđivanje + PTR preko routera + OISD Big (244k pravila) + querylog 7 d / stats 30 d postavljeni kroz API (skripta `~/.config/adguard/adguard-setup.sh`), admin lozinka u `~/.config/adguard/admin-pass`. Longhorn volumen u grupi nightly-b. Restart poda izmjeren: 12.5 s bez DNS-a. L2: .244 oglašava čvor na kojem je pod (eTP Local radi).
Napomena: za privatne PTR upite AdGuard NE koristi `[/1.168.192.in-addr.arpa/]` upstream pravilo nego `use_private_ptr_resolvers` + `local_ptr_upstreams: [192.168.1.1]` (postavljeno). PodSecurity `restricted` warning kod rollouta — isto kao ostali appovi (root image), ignorirano.
Router 2.10.: statički leaseovi printer .60 / BLE proxy .61 / Gree .62, pool end .239, DHCP DNS `192.168.1.1,192.168.1.244` (test). BLE proxy već na .61 (restart iz HA), printer i Gree sele se same pri obnovi leasea (≤24 h).
Korak 5 GOTOV 2.10.: Authentik proxy provider `adguard-proxy` pk 20, app slug `adguard`, outpost [8..20] (preko API-ja s privremenim tokenom; skripta `~/.config/adguard/ak/run.sh`, token obrisan lokalno; Zlatan ga obrisao i u Authentiku 2.10. navečer). `adguard.zlayahome.ovh` → 302 na Authentik login OK.
Korak 6 GOTOV 2.10. ~15:00: router DHCP DNS = `192.168.1.244,192.168.1.1`; managment VM nakon renew + restart systemd-resolved rješava kroz AdGuard (zeus.home, nas.home, k8s.home, doubleclick → 0.0.0.0, homeassistant.home preko routera). Napomena: systemd-resolved drži 'current server' dok ne zakaže — nakon promjene redoslijeda treba restart resolveda ili čekati ispad.
Tailscale split DNS `home → 192.168.1.244` dodan 2.10. ~15:10 (admin konzola, Zlatan); propagacija ~1 min + flush cachea na Macu; `https://zeus.home:8006` s MacBooka izvan LAN-a RADI. Tailscale klijenti u AdGuard statistici = managment.home (.199, SNAT subnet routera).
Homepage 2.10. (commiti 51292da, a7335f0): AdGuard widget (Servers), nova grupa Apps s Immich widgetom (API key server.statistics u SOPS secretu) i BookOrbit karticom (siteMonitor; BookOrbit nema token API). Vidi zapis u ~/projects/HOMELAB-STATUS-2026-10-02.md.
Printer preseljen na .60 2.10. ~22:57 (restart; HA IPP se sam spojio preko zeroconfa). Gree još na .252 — čeka obnovu leasea.
**Cold-boot test BESPREDMETAN** (provjereno 2.10. navečer): Talos čvorovi uopće ne koriste .244 — vidi "Talos čvorovi i cold boot".
**Ostalo:** korak 8 (audit; Homepage widget gotov), Gree .62, faza 2.

Cilj faze 1: kućni DNS s blokiranjem reklama i lokalnim imenima (Proxmox, TrueNAS, router, k8s API…) pod `.home`.
Immich/Tailscale split DNS je zasebna faza 2, kad faza 1 bude stabilna.

## Odluke

| Stavka | Odluka | Zašto |
|---|---|---|
| Gdje | k8s, Flux, raw manifesti (uzorak = tautulli) | kao svi ostali appovi, Longhorn backup, Authentik ispred UI-ja |
| Verzija | `adguard/adguardhome:v0.107.79` (18.8.2026, zadnja stabilna), pin digest `sha256:aba9e3bf0613be3ba3755e1fc311b126e2c24bec25e18b6483894a88283074f0` | 0.108/1.0 su beta (novi UI), ne diramo |
| DNS IP | `192.168.1.244` (Cilium LB pool .240/28; zauzeto .240 main, .241 plex, .242 immich-lan, .243 public) | fiksan IP koji router dijeli preko DHCP-a |
| Tko dijeli DNS | router 192.168.1.1 (Technicolor Homeware 19.5, ISP skin, bez SSH-a) preko DHCP-a: **`192.168.1.244,192.168.1.1`** — AdGuard primarni, router rezerva | Zlatanov zahtjev 2.10.: kad je cijeli rack ugašen (struja, servis) kuća mora imati internet → rezerva mora biti izvan racka = router. Cijena: dio upita (Android/TV, Windows ~15 min nakon ispada) ide na router bez blokiranja. TESTIRANO 2.10.: polje DNS server prima dvije LAN adrese odvojene zarezom (javne odbija), klijent dobiva obje. Trenutno u routeru `192.168.1.1,192.168.1.244` (bezopasno dok .244 ne postoji); u koraku 6 samo okrenuti redoslijed. |
| Lokalna domena | `.home` | router već daje `search home` svim DHCP klijentima i rješava DHCP imena (`managment.home`, `homeassistant.home`, `ubuntu-media.home`) — AdGuard to prosljeđuje routeru, a statičke hostove dodaje rewriteom |
| Web UI | `adguard.zlayahome.ovh` → Authentik proxy-private (Gateway main .240, grey A zapis radi external-dns) | isti model kao tautulli/radarr; AdGuard login ostaje kao drugi sloj (treba za API) |
| Replike | 1 (Recreate, RWO PVC), tolerationSeconds ~30 s da seljenje kod pada čvora traje ~1 min umjesto 5 | druga instanca u racku (k8s ili ubuntu-media) ODBAČENA 2.10.: ne pomaže kad je cijeli rack dolje; rezerva je router |

## Arhitektura

- Namespace `adguard`, Deployment 1 replika, PVC `adguard-data` 1Gi Longhorn (`/opt/adguardhome/conf` + `/opt/adguardhome/work`), requests 50m/128Mi, limit 512Mi.
- Service `adguard-dns` type LoadBalancer, anotacija `lbipam.cilium.io/ips: 192.168.1.244`, portovi 53/UDP + 53/TCP (mixed-protocol LB je GA), `externalTrafficPolicy: Local` → AdGuard vidi prave klijentske IP-ove (statistika po uređaju). Cilium L2 kod Local oglašava IP samo s čvora na kojem je pod (dokumentirano), pa nema crne rupe.
- Service `adguard-web` ClusterIP 80 → backend za Authentik outpost (`internal_host http://adguard-web.adguard.svc.cluster.local`).
- Pod `dnsPolicy: None`, `dnsConfig.nameservers: [1.1.1.1, 9.9.9.9]` — AdGuard ne smije rješavati vlastite upstreame kroz sebe (čvorovi će preko DHCP-a dobiti .244 kao prvi resolver).
- Readiness/liveness: TCP 53 (nakon wizarda), startupProbe duža jer prvi start sluša na 3000.

### Talos čvorovi i cold boot
**Ispravka 2.10. navečer** — prvobitna pretpostavka ("kad router počne dijeliti .244, lista postaje `[.244, .1, 1.1.1.1, 8.8.8.8]`" → testirati cold boot) bila je pogrešna. Čvorovi su na DHCP-u, ali imaju i statične nameservere u `infrastructure/talos/patch-all.yaml` (`machine.network.nameservers: [192.168.1.1, 1.1.1.1, 8.8.8.8]`). Talos slaže resolvere po layerima i **statični config (`configuration`) pobjeđuje DHCP (`operator`)**:
- `talosctl get resolverspecs --namespace network-config` → `dhcp4/ens18/resolvers = [192.168.1.244, 192.168.1.1]` na .135 i .143 (DHCP već dijeli .244; hades još na starom leaseu),
- `talosctl get resolvers` → konačna lista je samo statična `[.1, 1.1.1.1, 8.8.8.8]`, layer `configuration` — **.244 nije u njoj i neće biti**.

Lanac u klasteru: pod → CoreDNS (`forward . /etc/resolv.conf`) → Talos hostDNS `169.254.116.108` (`forwardKubeDNSToHost: true`) → statična lista čvora. Čvor sam (kubelet, image pull) → hostDNS `127.0.0.53` → ista lista. AdGuard pod → direktno 1.1.1.1/9.9.9.9 (`dnsPolicy: None`).

Posljedice:
- **Nema kružne ovisnosti** (AdGuard živi u klasteru koji bi ga koristio za DNS) → hladan start i pad hadesa ne usporavaju DNS klastera. Cold-boot test i "opcija B" (statični nameserveri) su bespredmetni — B je de facto već uključen.
- Podovi ne rješavaju AdGuard rewriteove (`nas.home`, `zeus.home`, `k8s.home`); DHCP `.home` imena (`homeassistant.home`, `managment.home`) rade preko routera. Blokiranje reklama klasteru ne treba; AdGuard statistika je bez šuma klastera.
- Kozmetika: na čvorovima je lista od 6 resolvera (iste 3 dvaput) jer je patch primijenjen dvaput i liste su se nadovezale; u repou su 3. Bezopasno; čišćenje = `apply-config` bez reboota, nije nužno.

### AdGuard konfiguracija (UI, korak 3)
- Upstream (parallel): `https://dns.cloudflare.com/dns-query`, `https://dns.quad9.net/dns-query`; bootstrap `1.1.1.1`, `9.9.9.9`.
- Uvjetno prosljeđivanje routeru (DHCP imena + PTR za imena klijenata u statistici):
  `[/home/]192.168.1.1` i `[/1.168.192.in-addr.arpa/]192.168.1.1`
- DNS rewrites (statički hostovi koje router ne zna):
  | ime | IP |
  |---|---|
  | router.home | 192.168.1.1 |
  | zeus.home, proxmox.home | 192.168.1.10 |
  | hades.home | 192.168.1.20 |
  | poseidon.home | 192.168.1.30 |
  | nas.home, truenas.home | 192.168.1.101 |
  | k8s.home (API VIP) | 192.168.1.100 |
  | adguard.home | 192.168.1.244 |
  (ha.home nije potreban: `homeassistant.home` dolazi iz DHCP-a; po želji rewrite `ha.home → .179`.)
- Filteri: AdGuard DNS filter (default) + OISD Big (`https://big.oisd.nl`). Ne gomilati liste; HaGeZi Pro tek ako OISD propušta.
- Rate limit: 0 (isključen) ili whitelist čvorova .135/.136/.143 — CoreDNS iz klastera dolazi s IP-a čvora i lako pređe default 20 req/s.
- Query log 7 dana, statistika 30 dana (sve na Longhorn PVC-u, mala pisanja).
- DHCP server u AdGuardu: ISKLJUČEN (router ostaje DHCP).
- Napomena: Proxmox/TrueNAS imena pod `.home` daju self-signed TLS upozorenje u browseru kao i IP-ovi danas; valjani certovi kroz Gateway su posebna tema.

## Koraci

0. **Provjera routera prije svega.** Technicolor UI → Local Network / DHCP: postoji li polje DNS server za DHCP klijente. Ako ne postoji u GUI-ju, treba root/SSH i dnsmasq `dhcp_option='6,192.168.1.244'` u `/etc/config/dhcp`. Bez ovoga faza 1 pada na ručno postavljanje DNS-a po uređaju — tada stani i javi.
1. **Git**: `kubernetes/apps/adguard/{namespace,pvc,deployment,service,kustomization}.yaml` + `kubernetes/flux/adguard.yaml` (dependsOn longhorn, gateway) + `adguard.zlayahome.ovh` u `kubernetes/apps/authentik/httproute-proxy-private.yaml`. Commit, push, Flux (≤1 min).
2. **Prvi setup** (ODLUKA 2.10.: config kroz UI/PVC, NE u gitu): `kubectl -n adguard port-forward deploy/adguard 3000:3000` → wizard: web port 80, DNS port 53, admin user. Config ostaje na PVC-u (nije u gitu; backup kroz Longhorn). Početne postavke iz koraka 3 unosim kroz AdGuard API, ne ručno. Volume CR labelirati `recurring-job-group.longhorn.io/nightly-b=enabled` (grupa b ima 4 volumena, najmanja).
3. **Konfiguracija** po tablici gore.
4. **Test s managment VM-a** (prije diranja routera):
   `dig @192.168.1.244 google.com` (odgovor + vrijeme), `dig @192.168.1.244 zeus.home`, `dig @192.168.1.244 managment.home` (prosljeđivanje routeru), `dig @192.168.1.244 -x 192.168.1.179`, `dig @192.168.1.244 doubleclick.net` (očekivano 0.0.0.0/NXDOMAIN), TCP: `dig +tcp @192.168.1.244 google.com`.
   Pod restart: `kubectl -n adguard rollout restart deploy/adguard` i mjeriti koliko sekundi DNS ne odgovara (očekivano 10–20 s).
   ~~Cold-boot test: `kubectl -n adguard scale deploy/adguard --replicas=0`, pa `dig` iz poda u klasteru i s čvora → mora proći kroz fallback; vratiti na 1.~~ BESPREDMETNO — čvorovi ne koriste .244 (vidi "Talos čvorovi i cold boot").
5. **Authentik**: Admin → Providers → novi Proxy provider `adguard` (external host `https://adguard.zlayahome.ovh`, internal `http://adguard-web.adguard.svc.cluster.local`), Application, dodati u embedded outpost; restart `authentik-server` (poznato ponašanje). Test logina.
6. **Router**: DHCP DNS = `192.168.1.244,192.168.1.1` (okrenuti redoslijed; danas stoji obrnuto). Na managment VM-u `sudo networkctl renew enp6s18` ili reboot klijenata; provjera `resolvectl status` → DNS .244, search `home`. AdGuard dashboard pokazuje klijente po IP-u/imenu.
7. **Statički hostovi** (Proxmox ×3, TrueNAS) ostaju na .1 — nije nužno mijenjati; po želji ručno na .244.
8. **Nakon tjedan dana**: provjeriti statistiku (lažno blokirano → allowlist), vrijeme odgovora, Longhorn backup volumena; dodati AdGuard widget na Homepage (ima nativni `adguard` widget; treba URL + user/pass u secretu); u mjesečni audit dodati `adguard/adguardhome` tag.

## Rollback
Router DHCP DNS natrag na `192.168.1.1` (ili `192.168.1.1,192.168.1.244` kao danas) → klijenti pri idućem lease renewu idu kao danas. k8s dio može ostati, nikog ne smeta.

## Rizici
- Jedan pod: restart/upgrade = 10–20 s, pad čvora ≈1 min (s tolerationSeconds) — za to vrijeme uređaji padaju na router (internet radi, reklame prolaze) i neki se vraćaju na AdGuard tek za ~15 min. Prihvaćeno 2.10.
- Rack ugašen: sve ide na router, internet radi bez blokiranja i bez `.home` imena statičkih hostova (DHCP imena rade).
- Lažno pozitivni filteri (OISD je konzervativan, zato samo on na početku).
- ~~Čvorovi dobivaju .244 preko DHCP-a~~ — dobivaju ga, ali ga ne koriste: statični nameserveri imaju prednost (vidi cold boot gore).

## Faza 2 (poslije, zasebno)
Tailscale split DNS za `zlayahome.ovh` → AdGuard; rewrite `photos.zlayahome.ovh → 192.168.1.240`; Immich HTTPRoute dodati `main/https-ovh` parentRef. Tada Tailscale DNS i `.home` imena rade i s puta.
