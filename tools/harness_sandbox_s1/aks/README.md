# S1 na AKS – microVM hranice (Kata) a gVisor

Tahle část harnessu S1 se nedá spustit v cloudovém kontejneru bez `/dev/kvm`. Skript `run-s1-aks.sh` ji provede
na AKS: node pool s nested virtualizací, Pod Sandboxing (Kata, `kata-vm-isolation`), pod s `sandbox-runtime` uvnitř
a stejné kontroly jako lokální S1a–S1d, navíc S1h (hranice microVM) a start/hustota.

Předpoklady: `az` přihlášené, subscription s povolenou nested virtualizací pro gen2 SKU (viz
[`../../../knowledge/sandbox/overview.md`](../../../knowledge/sandbox/overview.md), síto skupina A),
`kubectl`, `helm`. **Spouští Adam ručně; výsledky uloží jako `results/aks-<datum>.json`.**

```bash
export RG=rg-harness-s1 LOC=westeurope CLUSTER=aks-harness-s1
./run-s1-aks.sh create     # cluster + Kata node pool (Dsv5, Azure Linux) – ~15 min
./run-s1-aks.sh run        # nasadí pod-kata.yaml + pod-gvisor.yaml (pokud RuntimeClass runsc existuje), spustí kontroly
./run-s1-aks.sh destroy
```

Co skript měří (zapisuje do JSON):

| Check | Tvrzení |
|---|---|
| S1h-1 | pod s `runtimeClassName: kata-vm-isolation` běží; `uname -r` uvnitř ≠ kernel uzlu (vlastní guest kernel) |
| S1h-2 | start podu (PodScheduled → Ready) pro Kata vs. runc, 10 opakování, medián |
| S1h-3 | `srt` uvnitř Kata podu bez `enableWeakerNestedSandbox`: bwrap mount `/proc` projde (user namespaces v guest kernelu) |
| S1h-4 | NetworkPolicy default-deny egress + allow jen na agentgateway: `curl https://pkg…` mimo gateway selže, přes gateway projde |
| S1h-5 | SPIRE (pokud nasazen): SVID per pod z `k8s:pod-uid` selectoru – INFO |
| S1h-6 | RAM overhead per Kata pod (`kubectl top` vs. limit) – INFO |

Soubory: `pod-kata.yaml` (pod s obrazem `node:22-bookworm` + bubblewrap + srt, non-root, `automountServiceAccountToken: false`),
`networkpolicy.yaml` (default-deny egress + allow kube-dns + allow agentgateway), `pod-gvisor.yaml` (totéž s `runsc`,
jen pokud je RuntimeClass nainstalovaná – AKS gVisor nativně nenabízí).
