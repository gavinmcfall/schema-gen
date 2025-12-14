---
description: System architecture covering extraction pipeline, source types, and deployment
tags: ["ExtractionPipeline", "SourceTypes", "CloudflarePages", "JSONSchema"]
audience: ["LLMs", "Humans"]
---

# Architecture Overview

## Core Pattern

### Capsule: ExtractionPipeline

**Invariant**
CRDs are fetched from sources, converted to JSON Schema, enriched with provenance metadata, and published.

**Example**
Source `flux` (Helm type) → fetch chart → extract CRDs → convert to JSON Schema → save to `schemas/source.toolkit.fluxcd.io/v1/gitrepository.json`

**Depth**
- Distinction: We convert OpenAPI schemas (in CRDs) to JSON Schema (for IDEs)
- Trade-off: Static extraction vs runtime discovery; we chose static for simplicity
- NotThis: We don't run operators or query live clusters
- SeeAlso: `SourceTypes`, `ProvenanceMetadata`

---

### Capsule: SourceTypes

**Invariant**
Four source types exist, organized in directories for native Renovate support:
- `helm` → `sources/helm/{name}/helmrelease.yaml`
- `kustomize` → `sources/kustomize/{name}/kustomization.yaml`
- `github` → `sources/github/{name}/source.yaml`
- `url` → `sources/url/{name}/source.yaml`

**Example**
```yaml
# sources/helm/flux/helmrelease.yaml
repository: oci://ghcr.io/fluxcd-community/charts
chart: flux2
version: "2.14.1"

# sources/kustomize/cilium/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - https://github.com/cilium/cilium//pkg/k8s/apis/cilium.io/client/crds?ref=v1.17.0

# sources/github/gateway-api/source.yaml
# renovate: datasource=github-releases depName=kubernetes-sigs/gateway-api
repository: kubernetes-sigs/gateway-api
version: v1.2.1
assets:
  - standard-install.yaml

# sources/url/hierarchical-namespaces/source.yaml
# renovate: datasource=github-releases depName=kubernetes-retired/hierarchical-namespaces
url: https://github.com/.../releases/download/{version}/default.yaml
version: v1.1.0
```

**Depth**
- Distinction: Directory structure enables native Renovate managers
- Trade-off: More files but automatic version updates via Renovate
- Benefit: `helmrelease.yaml` and `kustomization.yaml` are standard formats

---

### Capsule: ProvenanceMetadata

**Invariant**
Every schema includes `x-kubernetes-schema-metadata` with source name, version, and extraction timestamp.

**Example**
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://k8s-schemas.io/source.toolkit.fluxcd.io/v1/gitrepository.json",
  "x-kubernetes-schema-metadata": {
    "sourceName": "flux",
    "sourceVersion": "2.14.1",
    "extractedAt": "2025-12-14T02:17:02.209902+00:00",
    "generator": "k8s-schemas.io"
  }
}
```

**Depth**
- Distinction: Provenance enables tracking which source provided which schema
- Trade-off: Extra metadata but enables debugging and updates
- SeeAlso: `SchemaDeduplication`

---

## Extraction Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ sources/    │────▶│ extract.py  │────▶│ common.py   │────▶│ schemas/    │
│ helm/       │     │             │     │ (convert)   │     │ {group}/    │
│ kustomize/  │     │ - fetch CRDs│     │             │     │ {version}/  │
│ github/     │     │ - parse YAML│     │ - strip k8s │     │ {kind}.json │
│ url/        │     │             │     │   extensions│     │             │
└─────────────┘     └─────────────┘     │ - add meta  │     └─────────────┘
                                        └─────────────┘
```

### Step-by-Step

1. **Load sources** - Scan directory structure to find all source definitions
2. **Fetch CRDs** - Based on source type:
   - `helm`: Run `helm template` with `--include-crds`
   - `kustomize`: Fetch from GitHub path in kustomization.yaml
   - `github`: Fetch assets from GitHub releases
   - `url`: Download directly with version substitution
3. **Parse YAML** - Extract CRD documents from multi-document YAML
4. **Convert to JSON Schema** - Transform OpenAPI to JSON Schema:
   - Strip Kubernetes-specific extensions (`x-kubernetes-*`)
   - Add standard JSON Schema fields (`$schema`, `$id`, `title`)
   - Add provenance metadata
5. **Save** - Write to `schemas/{group}/{version}/{kind}.json`

---

## Directory Structure

```
schema-gen/
├── sources/                  # Source definitions (Renovate-managed)
│   ├── helm/                 # Helm chart sources
│   │   ├── flux/
│   │   │   └── helmrelease.yaml
│   │   └── cert-manager/
│   │       └── helmrelease.yaml
│   ├── kustomize/            # GitHub sources with crd_path
│   │   └── cilium/
│   │       └── kustomization.yaml
│   ├── github/               # GitHub release assets
│   │   └── gateway-api/
│   │       └── source.yaml
│   └── url/                  # Direct URL sources
│       └── hierarchical-namespaces/
│           └── source.yaml
├── scripts/
│   ├── extract.py            # Main extraction orchestrator
│   ├── common.py             # Shared utilities (parsing, conversion)
│   ├── generate_index.py     # Web interface index generator
│   └── detect_changes.py     # CI change detection
├── schemas/                  # OUTPUT: Extracted JSON schemas
│   ├── source.toolkit.fluxcd.io/
│   │   └── v1/
│   │       └── gitrepository.json
│   └── ...
├── public/
│   └── index.html            # Web interface
├── tests/
│   ├── conftest.py           # Pytest fixtures
│   ├── test_common.py        # Unit tests
│   └── test_extract.py       # Integration tests
└── .github/workflows/
    ├── extract.yaml          # CI extraction on source changes
    ├── publish.yaml          # Deploy to Cloudflare Pages
    └── test.yaml             # Run tests on PR
```

---

## Deployment

### Capsule: CloudflarePages

**Invariant**
Schemas are deployed as static files to Cloudflare Pages; the web interface loads `schemas-index.json` for navigation.

**Example**
Push to `main` → GitHub Actions → `wrangler pages deploy` → https://k8s-schemas.nerdz.cloud

**Depth**
- Distinction: Static hosting, no server-side processing
- Trade-off: Simple deployment but requires full rebuild for updates
- NotThis: Not a dynamic API; schemas are pre-generated

---

## Key Files

| File | Purpose |
|------|---------|
| `sources/helm/*/helmrelease.yaml` | Helm source definitions |
| `sources/kustomize/*/kustomization.yaml` | Kustomize source definitions |
| `sources/github/*/source.yaml` | GitHub release sources |
| `sources/url/*/source.yaml` | URL sources |
| `scripts/extract.py` | Orchestrates extraction |
| `scripts/common.py` | CRD parsing and schema conversion |
| `scripts/generate_index.py` | Generates web interface index |
| `public/index.html` | Web interface for browsing schemas |

---

## Evidence

| Claim | Source | Confidence |
|-------|--------|------------|
| Four source types | `sources/` directory structure | Verified |
| Provenance metadata format | `scripts/common.py:112-120` | Verified |
| Cloudflare Pages deployment | `.github/workflows/publish.yaml` | Verified |
