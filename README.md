# Homelab

GitOps repository for my homelab Kubernetes cluster.

## Stack
- **OS**: Talos Linux v1.12.4
- **Kubernetes**: v1.35.0
- **CNI**: Cilium v1.18.7
- **GitOps**: Flux CD
- **Secrets**: SOPS + age
- **Storage**: Longhorn + TrueNAS NFS

## Nodes
| Node | Host | IP | RAM |
|---|---|---|---|
| talos-icw-nam | zeus | 192.168.1.143 | 64GB |
| talos-pv0-ntu | poseidon | 192.168.1.135 | 32GB |
| talos-zij-wro | hades | 192.168.1.136 | 48GB |

## VIP
- API endpoint: 192.168.1.100
