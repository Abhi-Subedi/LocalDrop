# ADR-010 — License: AGPL-3.0

**Status:** **Accepted — ratified by maintainer, 2026-10-01 (D1 resolved).**
**Date:** 2026-09-30 (proposed) · 2026-10-01 (ratified).

## Context

LocalDrop is an open-source, self-hosted product. License choice shapes who
contributes, who deploys, and whether someone can take the code, close it, and sell
it back to our users as a hosted service.

## Options

| | License | Strengths | Weaknesses |
|---|---|---|---|
| A | **MIT** | Maximum adoption & corporate comfort; zero friction | Anyone can run a closed fork/SaaS with zero reciprocity; brand confusion risk |
| B | **Apache-2.0** | MIT-like + explicit patent grant | Still permissive on the network-service loophole; longer text |
| C | **AGPL-3.0** | Copyleft that closes the **hosted-service loophole** (§13 network use = source disclosure); protects the project's name/community from proprietary reselling | Some companies ban AGPL by policy (few would embed a file server anyway); marginally higher friction for corporate contributors; not "fully" resellable — which is the point |
| D | **AGPL + CLA** | C plus relicensing optionality | CLAs repel exactly the community self-hosted projects live on; a one-maintainer CLA is overhead theater |

Precedent in the self-hosted ecosystem runs both ways (Nextcloud/Grafana-class AGPL;
Paperless/MIT) — both models demonstrably work; the question is the founder's intent
for *this* project.

## Decision (ratified)

**AGPL-3.0-only, no CLA (option C)** — ratified 2026-10-01. The `LICENSE` file in the
repository root is the canonical AGPL-3.0 text. Rationale: LocalDrop's whole
proposition is
"your server, your data" — a proprietary hosted fork extracting unpaid work while
competing with the community version contradicts the project's thesis (P2); AGPL
prices that in at zero cost to normal self-hosters and typical contributors. D (CLA)
rejected: contribution friction without realistic benefit at this scale.

**Consequences**

- **+** Hosted-fork free-riding is legally off the table; users get source rights
  even from SSB (self-software-built) deployments.
- **+** Deterrence is passive — no policing burden for a small team.
- **−** Some corporate deployments will pass (measured, accepted: they weren't
  contributing either).
- **−** Must keep the license header/notice discipline (one file, CI check) and
  vendor bundled assets (fonts) under compatible terms (checked at Phase 1).
