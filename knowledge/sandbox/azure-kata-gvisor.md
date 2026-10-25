---
tema: Kata Containers a gVisor na Azure/AKS – AKS Pod Sandboxing, kata-deploy, egress a cena (kolo 2, hloubka A)
naposledy_overeno: 2026-10-23
zralost: GA (AKS Pod Sandboxing, gVisor, Kata); srt/Chromium uvnitř neměřeno (harness S1 část aks/)
primarni_zdroje:
  - https://github.com/MicrosoftDocs/azure-aks-docs/blob/main/articles/aks/use-pod-sandboxing.md
  - https://github.com/MicrosoftDocs/azure-aks-docs/blob/main/articles/aks/considerations-pod-sandboxing.md
  - https://github.com/MicrosoftDocs/azure-aks-docs/blob/main/articles/aks/concepts-pod-sandboxing.md
  - https://github.com/MicrosoftDocs/azure-aks-docs/blob/main/articles/aks/support-policies.md
  - https://github.com/MicrosoftDocs/azure-aks-docs/blob/main/articles/aks/container-network-security-fqdn-filtering-concepts.md
  - https://github.com/MicrosoftDocs/azure-aks-docs/blob/main/articles/aks/use-network-policies.md
  - https://github.com/MicrosoftDocs/azure-compute-docs/blob/main/articles/virtual-machines/sizes/general-purpose/dadsv7-series.md
  - https://github.com/Azure/AKS/releases
  - https://github.com/microsoft/azurelinux/tree/3.0/SPECS (kernel, kernel-mshv, kernel-uvm, kata-containers, cloud-hypervisor)
  - https://github.com/microsoft/kata-containers (tag 4.1.0.kata0)
  - https://github.com/kata-containers/kata-containers (docs/install, docs/hypervisors.md, docs/Limitations.md, src/runtime/Makefile, kata-deploy helm values, issue #8170)
  - https://github.com/google/gvisor (g3doc/user_guide/platforms.md, compatibility.md, pkg/sentry/syscalls/linux/linux64.go, issues #13303, #14033, PR #14996)
---

# Kata a gVisor na Azure/AKS

Kolo 2, hloubka A (2026-10-23). Navazuje na síto v [overview.md](overview.md); kritéria v [kriteria.md](kriteria.md).
Weby learn.microsoft.com, azure.com pricing, prices.azure.com, katacontainers.io byly nedostupné → fakta z raw docs
repozitářů (`ms.date` uvedeno), Azure Linux SPECS a GitHub releases; ceny jen *sek.*

## Závěr

- **AKS Pod Sandboxing je GA bez feature flagu** – docs (ms.date 10/02/2026) neobsahují preview ani `az feature register`;
  prereq jen Azure CLI ≥ 2.80.0, K8s ≥ 1.27.0. GA oznámení Ignite 11/2025 a Kata blog 02/2026 jen *sek.*
- Stack: Azure Linux 3.0 + **Hyper-V (`/dev/mshv`, `kernel-mshv` 6.6.137.mshv2) + Cloud Hypervisor 52.0.152 (MS fork, `--features mshv`)
  + Kata 4.1.0.kata0 (MS fork; upstream je 4.3.1)**; guest kernel `kernel-uvm` 6.6.137.mshv1. OpenVMM jen v kódu forku, ne v docs.
- Pod VM = memory limit (default **512Mi**, min 128Mi, +≈88Mi overhead), CPU **zaokrouhleno nahoru**; bez samostatného meteru → platí se uzel.
- **Uvnitř Kata podu na AKS:** `USER_NS=y`, `SECCOMP_FILTER=y`, **Landlock ne**, AppArmor ne, `seccompProfile` z podu se
  standardně neaplikuje (`disable_guest_seccomp = true` upstream default; MS fork neověřen), `hostUsers: false` nepodporováno (#8170).
  srt uvnitř je tedy **jediný seccomp v guestu** – a nemá proti sobě RuntimeDefault, který by bwrap blokoval (viz [anthropic-sandboxing.md](anthropic-sandboxing.md)).
- **gVisor na AKS nativně není**; vlastní privileged DaemonSet (support policy: tolerováno, bez troubleshootingu, nepřežije upgrade
  → idempotentní + taint). `systrap` bez nested virt, doporučen ve VM. `hostUsers: false` ne (#13303), nested userns + overlay bug #14033.
- **Egress:** FQDN jen ACNS (placené, Azure CNI powered by Cilium, K8s ≥ 1.29; CCNP ano, L7 v CCNP ne) → **nepoužít**,
  stačí CNP L3/L4 na agentgateway; jména hlídá gateway ([egress-agentgateway.md](egress-agentgateway.md)).

## AKS Pod Sandboxing

| Oblast | Fakt (zdroj, ms.date) |
|---|---|
| Stav | GA; docs bez preview/flagu (use-pod-sandboxing.md 10/02/2026; commit 2026-10-02 odstranil jen obsoletní registraci BYO IP); AKS releases: 2023-02-26 preview, 2025-08-29 `kata-vm-isolation`, 2025-09-21 rename z `kata-mshv-vm-isolation`, 2026-04-28 Artifact Streaming blokován, 2026-06-19 FIPS odmítnut + **Dadsv7 povoleno** |
| Vytvoření | `az aks create --os-sku AzureLinux --workload-runtime KataVmIsolation --node-vm-size Standard_D4s_v3` („generation 2 VM size that supports nested virtualization“); nodepool add + `az aks update`; pod `runtimeClassName: kata-vm-isolation` + nodeSelector `kubernetes.azure.com/agentpool` |
| Omezení | jen Azure Linux; bez host network; FIPS/Trusted Launch ne; Arm64 ne; Defender neassessuje; IOPS Azure Files/local SSD nižší; Windows ne; GPU v docs nikde (CLH „GPU: No“) |
| Zdroje VM | considerations (09/17/2026): memory limit → VM, default 512Mi, < 128Mi ne, fixní po startu; `kata-vm-isolation` ≈ 88Mi overhead; CPU limit → vCPU nahoru („account for this when planning cost and node density“) |
| hostPath | povolen, „can weaken isolation“; `/dev` z guestu; Azure Policy allowed volume types Deny |
| emptyDir | upstream `disable_guest_empty_dir := true` + `emptydir_mode` → hostitelský adresář přes virtio-fs (ověřit v harnessu; dopad: pracovní data agenta na hostu → cleanup) |
| PVC | Azure Files CSI confidential mounts (AKS 2025-04-06); `subPath` Kata nepodporuje |
| securityContext | privileged povolen = root v guestu, host devices ne; `seccompProfile` v guestu default neaplikován (`DEFDISABLEGUESTSECCOMP := true`); `hostUsers: false` ne (Kata #8170 otevřené od 2023, bez PR; blocker virtiofs idmap) |
| Kernel | host `kernel-mshv` 6.6.137.mshv2: `MSHV_ROOT=y`, **`KVM` not set** (upstream `kata-qemu`/`kata-clh` tam nepoběží), Landlock=y; guest `kernel-uvm` 6.6.137.mshv1: `USER_NS/PID_NS/NET_NS=y`, `SECCOMP_FILTER=y`, **`SECURITY_LANDLOCK` not set**, AppArmor/AUDIT/VIRTUALIZATION not set, `VIRTIO_FS=y` |
| Identita | SPIRE `k8s` workload attestor běží přes kubelet na hostu → pod-label/pod-uid funguje i pro Kata pod; `unix` attestor (PID/cgroup) uvnitř VM ne |
| Cena | žádný meter v docs; jen SKU uzlu; hustotu snižuje CPU rounding + fixní RAM |

## gVisor na AKS

- Nativní podpora: žádná (AKS docs mlčí; custom node config jen kubelet/sysctl).
- Instalace: privileged DaemonSet → `runsc` + `containerd-shim-runsc-v1` vedle containerd (Azure Linux 3.0 `containerd2`), sekce
  `runtimes.runsc` v `/etc/containerd/config.toml`, restart containerd, RuntimeClass `gvisor`/`runsc`; taint do instalace.
  Support policy (08/27/2026): změny mimo AKS API nepřežijí upgrade/scale/reboot; DaemonSet tolerován, „can't help troubleshoot“;
  containerd je autoremediovaná komponenta. Azure Linux nemá gVisor apt repo → binárky z GitHub releases / interního registru.
- Platforma: `systrap` default („If you have to run gVisor within a virtual machine, the systrap platform will often yield better
  performance than KVM“); KVM jen bare-metal / nested virt („not recommended for production“) → bez nested-virt SKU, GPU uzly OK (`nvproxy`).
- Uvnitř (`linux64.go`): `clone/unshare` s `CLONE_NEWUSER|NEWPID|NEWNET|NEWNS` OK (ne time/cgroup ns); `seccomp` jen
  `SET_MODE_FILTER` s flags 0/TSYNC (Chromium OK; bwrap `prctl` částečně – ověřit); `landlock_*` ENOSYS; cgroupy jen účetní.
  **Bug #14033** (nested userns + overlay rename EPERM, 08/2026) – přesně scénář bwrap/srt nad overlay rootfs.
- `hostUsers: false`: #13303 otevřené, PR #14996 draft (09/2026).

## Kata upstream (`kata-deploy`) na Azure bez Pod Sandboxing

- „requires nested virtualization or bare metal“; SKU: Dsv3/Dsv5/Ddsv5/Dasv5/Esv5/Fsv2/Dadsv7 (compute-docs). Standardní Azure Linux kernel 6.6.157.1 má `KVM=m`.
- Helm values: shimy clh, clh-azure, clh-runtime-rs, clh-azure-runtime-rs, dragonball, qemu, qemu-runtime-rs, openvmm-azure-runtime-rs;
  default `qemu-runtime-rs`; fc jen `try-kata-fc.values.yaml` (devmapper); `k8sDistribution` bez `aks`; RuntimeClass overhead příklad 160Mi/250m.
- CLH: GPU/TDX/SNP ne; QEMU: ano („best supported hypervisor for NVIDIA-based GPUs“). Defaulty: `default_memory 2048`, `default_vcpus 1`,
  `disable_guest_seccomp true`, `static_sandbox_resource_mgmt` pro CLH Azure true. Limitations: bez `--net=host`, bez sdílení netns,
  privileged = jen v guestu, `subPath` ne, bez checkpoint/restore. Overhead měřený v docs není → harness.
- 4.3.1 (2026-10-21): agent libseccomp 2.6.0; userns ne.

## Egress na AKS

| Varianta | Požadavky | Limity | Cena |
|---|---|---|---|
| ACNS FQDN (`toFQDNs`) | Azure CNI powered by Cilium, K8s ≥ 1.29, `--enable-acns`; DNS `matchPattern` povinný | bez service names; > 1000 rps degradace; CCNP FQDN ano, L7 jen CNP (Envoy DaemonSet); bare `*` neověřeno; Alpine/musl workaround | „paid offering“, per node/hod, sazba nedostupná |
| **CNP/NetworkPolicy L3–L4 na agentgateway** | Cilium dataplane (Azure NPM Linux retired 2028-09-30) | jen IP/selektory → jména hlídá agentgateway | 0 |

Azure Linux 3.0 host kernel 6.6.157.1: Landlock=y (v `CONFIG_LSM`), `USER_NS=y`; `kernel.unprivileged_userns_clone` (Debian patch) neexistuje,
řídí jen `user.max_user_namespaces` (hodnota v AKS image neověřena). Kata pod nemá host network, ale IMDS síťově dosáhne → CNP default-deny
povinná i pod Katou (eval S-E3).

## Cena (*sek.*, 2026-10-23; Retail Prices API nedostupné)

| SKU / služba | West Europe Linux PAYG |
|---|---|
| D2s_v5 | ≈ $0.115/h (azurespeed) |
| D4s_v3 | ≈ $0.24/h (holori, 01/2026) |
| D4ads_v7 (nested virt, Gen2, 16 GiB) | ≈ $0.276/h (cloud-mercato/devzero) |
| ACA dynamic sessions built-in | ≈ $0.03/session-hour (East US), od alokace do dealokace po hodinách; custom = Dedicated E16 |
| Nested-virt příplatek | žádný meter; vlastnost SKU |

Všechny částky potvrdit z `prices.azure.com` (`armRegionName eq 'westeurope' and armSkuName eq '…' and priceType eq 'Consumption'`).

## Co ověřit dál

- [ ] Harness S1 na `kata-vm-isolation` ([`tools/harness_sandbox_s1/aks/`](../../tools/harness_sandbox_s1/aks/README.md)): `seccompProfile` skutečně neaplikován? pod s `hostUsers: false` – fail/ignore? srt bez `enableWeakerNestedSandbox`; Chromium sandbox; emptyDir na hostu; start a hustota per D4s_v5 vs D4ads_v7 vs gVisor systrap.
- [ ] Pod Sandboxing + Azure CNI powered by Cilium / Overlay (docs mlčí; agent-sandbox příklad kata-aks používá Cilium – *sek.*).
- [ ] Upstream `clh-azure` shim z kata-deploy na AKS bez `KataVmIsolation`; `user.max_user_namespaces` v AKS image.
- [ ] Ceny z `prices.azure.com` (D2s_v5/D4s_v5/D4ads_v7 WE, ACNS, dynamic sessions).
- [ ] gVisor #14033 stav v release-20261019.0; SPIRE k8s attestor pro Kata pod; Inspect chart `runtimeClassName` override.

## Changelog
- 2026-10-25: P1-6 – role jako Kata pody na AKS změřeny (start 1–2 s, egress z podu, srt weaker); SVID v Kata podu → P2.
- 2026-10-23: první verze – kolo 2 hloubka A.

## Měření na AKS (P1-1, 2026-10-25, Poland Central, `tools/harness_sandbox_s1/aks`)

| Check | Výsledek | Poznámka |
|---|---|---|
| S1h-1 vlastní guest kernel | PASS | uzel `6.6.137.mshv2-2.azl3`, guest `6.6.137.mshv1-1.azl3` (Kata nad Microsoft Hypervisorem, Azure Linux 3) |
| S1h-2 start Kata podu apply→Ready | 2,2–2,6 s (3×, obraz na uzlu) | první start s pullem 408 MB obrazu ~14 s navíc; alokace uzlu z 0 autoscalerem ~2–3 min |
| egress sandboxu | blokován | NetworkPolicy default-deny: `apt-get`/`npm` v podu „Network is unreachable“ → nástroje musí být v obrazu (`infra/images/sandbox-s1`) |
| S1h-3a srt (bwrap) jako uid 1000 | FAIL | `bwrap: Can't mount proc on /newroot/proc: Operation not permitted` – kontejner má maskovaný `/proc` (`procMount: Default`), nový procfs v userns vyžaduje plně viditelný `/proc`; `procMount: Unmasked` jen s `hostUsers: false`, které Kata na AKS nepodporuje (#13303) |
| S1h-3b srt jako root + CAP_SYS_ADMIN v guestu | FAIL | stejná chyba – bwrap vždy vytváří vlastní userns, pravidlo „plně viditelný /proc“ platí bez ohledu na capabilities |
| S1h-3c srt s `enableWeakerNestedSandbox: true` jako uid 1000 | funguje | netns jen `lo`, `NoNewPrivs: 1`, `Seccomp: 2`; chybí mount/pid izolace přes userns – v Katě ji nahrazuje VM |
| S1h-5 pod `hostUsers: false` + `procMount: Unmasked` | FAIL | `FailedCreatePodSandBox: can't set spec.hostUsers: false, RuntimeClass handler "kata" does not support user namespaces` (potvrzeno #13303) |

**P1-6 změřeno (2026-10-25, `tools/harness_p1_k8s --step p1-6`):** role zakázky běží jako Kata pody v ns `platform-roles` (uid 1000, bez SA tokenu, drop ALL, srt weaker režim z obrazu); pod role startuje 2 s (obraz na uzlu; první pod po scale-upu z 0: 82 s uzel + 102 s pull 400 MB obrazu a boot VM), běh role 11–12 s, egress ověřen z podu (internet timeout, gateway/paměť/aplikace open), zakázka clusterem end-to-end. SVID z SPIRE v Kata podu neřešeno (unix socket agenta přes hostPath do VM nevede → P2: spiffe-csi/agent v guestu nebo token exchange na gateway).

**Důsledek pro P1-6 (návrh, potvrzeno měřením):** v Kata podu na AKS je hranicí izolace VM; srt běží jen ve weaker režimu (síťová izolace + seccomp + no-new-privs),
userns/bwrap mount izolace není dostupná. Pro role pody: obraz s nástroji předem (bez egressu nelze instalovat), `enableWeakerNestedSandbox: true`,
egress výhradně přes agentgateway (NetworkPolicy), zápis jen do emptyDir/`/tmp` podu. Alternativa gVisor (`runsc`) na AKS není (RuntimeClass chybí).
| SKU | `Standard_D2ads_v7` v Poland Central jen zóna 1, `AllocationFailed`/`provisioning-state-failed` → `Standard_D4s_v5` (DSv5 kvóta 8 vCPU) | Dadsv7 pro Pod Sandboxing teoreticky OK (release notes 2026-06-19), prakticky bez kapacity |
