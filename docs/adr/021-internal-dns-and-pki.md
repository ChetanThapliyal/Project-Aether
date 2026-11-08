```text
================================================================================
ADR-021: Internal Service Naming and Certificate Strategy
================================================================================
```
- **Status:** Accepted (root CA lifetime fixed November 2026; naming implemented in Phase 04)
- **Date:** November 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** The K3s Gateway serves HTTPS with a wildcard certificate for `*.aether.local`, signed by an internal root CA (`aether-root-ca`) that cert-manager created with its defaults: a 90-day lifetime, and since cert-manager v1.18 a private-key rotation policy of `Always`. On its first renewal (25 Dec 2026) the root would have been reissued with a new key, invalidating every client that trusted the old one. No client trusts it yet, and no HTTPRoute serves real traffic, so both the CA lifetime and the naming scheme can still be changed for free.
- **Problem Statement:** Which names should internal HTTP services use, and where should their certificates come from, so that browsers and tools trust them without per-device setup and without exposing internal services to the internet?
- **Decision Drivers:**
  - *No trust distribution:* every laptop, phone and container that has to install a private root is a step that will be forgotten, and a root that has been distributed is expensive to rotate.
  - *Names that resolve consistently:* the suffix must behave the same on Linux, macOS, iOS and Android.
  - *No public exposure:* publicly trusted certificates mustn't need public DNS records pointing at internal addresses, or inbound access for validation.
  - *Reuse what already works:* the Proxmox host already gets its certificate through ACME DNS-01 against the same Cloudflare zone ([runbook](../runbooks/proxmox-acme-cloudflare-tls.md)).
- **Decision:**
  1. *Root CA lifetime (done now):* `aether-root-ca` gets `duration: 87600h` (10 years), `renewBefore: 720h`, and `privateKey.rotationPolicy: Never`. Renewals keep the same key and subject, so certificates the root has already signed stay valid. The wildcard leaf keeps cert-manager's defaults, because leaves should rotate.
  2. *Naming (Phase 04):* internal HTTP services move to `*.lab.chetan-thapliyal.cloud`. These names resolve only on internal DNS, to the Gateway's LAN address. No public A records are created.
  3. *Certificates (Phase 04):* a `ClusterIssuer` for Let's Encrypt with ACME DNS-01 through Cloudflare, using an API token scoped to that one zone and stored in SOPS. The Gateway gets a new wildcard Certificate from it. DNS-01 needs no inbound access, so nothing internal is exposed.
  4. *Internal CA stays* for non-HTTP needs (mTLS between services, internal tooling) where public trust doesn't matter.
- **Alternatives Considered:**
  - *Keep `*.aether.local` and the private CA:* rejected. `.local` is reserved for multicast DNS (RFC 6762), so resolution differs between operating systems, and every client would need the root installed.
  - *`*.home.arpa` (RFC 8375) and the private CA:* correct naming, but it still needs the root distributed to every client. Rejected for that reason alone.
  - *Public names with HTTP-01 validation:* rejected. It needs inbound HTTP from the internet to each name.
- **Consequences:**
  - Browsers trust internal services out of the box, and there is no root to distribute or rotate on clients.
  - Certificate Transparency logs publish the names that get certificates. Using one wildcard keeps individual service names out of those logs, though the `lab.` subdomain itself becomes public.
  - Internal DNS must answer for the `lab.` subdomain. If internal DNS fails, the names stop resolving even though the certificates are valid.
  - The Cloudflare token can edit DNS in that zone. It is scoped to one zone, stored in SOPS, and its use shows up in Cloudflare's audit log.
- **Fitness Functions:**
  - `aether-root-ca`'s key hash is the same before and after every renewal.
  - The Gateway's HTTPS listener reports `Programmed=True`.
  - In Phase 04, `curl https://<service>.lab.chetan-thapliyal.cloud` from a fresh device, with no root installed, succeeds without `-k`.
