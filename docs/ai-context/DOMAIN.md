---
description: Domain model covering source types, schema format, and business rules
tags: ["SourceTypes", "SchemaFormat", "BusinessRules", "CRDExtraction"]
audience: ["LLMs", "Humans"]
---

# Domain Model

## Core Rules

### Rule 1: Sources define what to extract

**Rule**: Every CRD source must be defined in `sources.yaml` with type, location, and version.

**Enforced By**: `extract.py` reads only from sources.yaml.

**Violation**: Undocumented sources won't be extracted.

### Rule 2: Schemas include provenance

**Rule**: Every generated schema includes `x-kubernetes-schema-metadata` with source name, version, and timestamp.

**Enforced By**: `common.py:crd_to_jsonschema()` adds metadata.

**Why**: Enables tracking which source provided which schema for debugging and updates.

### Rule 3: Schema paths follow API group structure

**Rule**: Schemas are saved as `{group}/{version}/{kind}.json` matching Kubernetes API structure.

**Enforced By**: `common.py:write_schema()` creates directory structure.

**Example**: `source.toolkit.fluxcd.io/v1/gitrepository.json`

---

## Source Types

### Helm Sources

**Purpose**: Extract CRDs from Helm charts.

**Fields**:
```yaml
- name: flux                    # Unique identifier
  type: helm
  repo: https://fluxcd-community.github.io/helm-charts
  chart: flux2                  # Chart name in repo
  version: "2.14.1"             # Specific version
```

**Extraction**: `helm template --include-crds`

**When to use**: Chart exists and includes CRDs in `crds/` directory.

### GitHub Sources

**Purpose**: Extract CRDs from GitHub releases.

**Fields**:
```yaml
- name: gateway-api
  type: github
  repo: kubernetes-sigs/gateway-api   # owner/repo
  version: v1.2.1
  asset: experimental-install.yaml    # Release asset filename
  # OR
  crd_path: config/crd/bases          # Path in repo (optional)
```

**Extraction**: GitHub API to fetch release asset or repo contents.

**When to use**: Project releases CRD YAML as GitHub release assets.

### URL Sources

**Purpose**: Extract CRDs from direct URLs.

**Fields**:
```yaml
- name: containerized-data-importer
  type: url
  url: https://github.com/.../releases/download/{version}/cdi-operator.yaml
  version: v1.61.0
```

**Note**: `{version}` is replaced with the version value.

**When to use**: CRDs available at predictable URL pattern.

---

## Schema Format

### JSON Schema Structure

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://k8s-schemas.io/{group}/{version}/{kind}.json",
  "title": "{Kind}",
  "description": "Schema for {Kind} CRD",
  "type": "object",
  "properties": {
    "apiVersion": { "type": "string", "const": "{group}/{version}" },
    "kind": { "type": "string", "const": "{Kind}" },
    "metadata": { "type": "object" },
    "spec": { ... },
    "status": { ... }
  },
  "x-kubernetes-schema-metadata": {
    "sourceName": "...",
    "sourceVersion": "...",
    "extractedAt": "...",
    "generator": "k8s-schemas.io"
  }
}
```

### Kubernetes Extension Handling

These OpenAPI extensions are **stripped** during conversion:
- `x-kubernetes-preserve-unknown-fields`
- `x-kubernetes-validations`
- `x-kubernetes-int-or-string`
- `x-kubernetes-embedded-resource`
- `x-kubernetes-list-type`
- `x-kubernetes-map-type`

**Why**: JSON Schema validators don't understand them; they cause validation errors.

---

## State Machines

### Extraction Lifecycle

```
┌─────────┐     ┌──────────┐     ┌───────────┐     ┌─────────┐
│ Pending │────▶│ Fetching │────▶│ Converting│────▶│ Saved   │
└─────────┘     └──────────┘     └───────────┘     └─────────┘
                     │                  │
                     ▼                  ▼
                ┌─────────┐       ┌─────────┐
                │ Failed  │       │ Skipped │
                │(network)│       │(no CRDs)│
                └─────────┘       └─────────┘
```

### CI/CD Flow

```
Push to main
     │
     ├── sources.yaml changed? ──▶ Extract workflow
     │                                  │
     │                                  ▼
     │                            Extract CRDs
     │                                  │
     │                                  ▼
     │                            Commit schemas/
     │                                  │
     └── schemas/ or public/ changed? ──┼──▶ Publish workflow
                                        │         │
                                        ▼         ▼
                                   Generate index
                                        │
                                        ▼
                                   Deploy to CF Pages
```

---

## Entity Relationships

### Source → Schema Relationship

| Entity | Cardinality | Example |
|--------|-------------|---------|
| Source | 1 | `flux` |
| CRD | 1..* | `GitRepository`, `HelmRelease`, `Kustomization` |
| Schema | 1 per CRD version | `gitrepository.json` (v1, v1beta2) |

### Schema Path Structure

```
schemas/
└── {apiGroup}/           # e.g., source.toolkit.fluxcd.io
    └── {apiVersion}/     # e.g., v1
        └── {kind}.json   # e.g., gitrepository.json (lowercase)
```

---

## Glossary

| Term | Definition |
|------|------------|
| **CRD** | Custom Resource Definition; extends Kubernetes API |
| **OpenAPI Schema** | Schema embedded in CRD's `spec.versions[].schema.openAPIV3Schema` |
| **JSON Schema** | Standard schema format for JSON validation (used by IDEs) |
| **Provenance** | Metadata tracking where a schema came from |
| **Source** | Configuration in sources.yaml defining where to extract CRDs |
| **API Group** | Kubernetes API grouping (e.g., `source.toolkit.fluxcd.io`) |

---

## Common Failures

### Source-Related

| Error | Cause | Fix |
|-------|-------|-----|
| 404 on asset | Wrong asset name or version | Check GitHub releases page |
| 0 CRDs extracted | Chart doesn't include CRDs | Check if CRDs are separate |
| Helm template fails | Invalid chart or version | Verify chart exists in repo |

### Schema-Related

| Error | Cause | Fix |
|-------|-------|-----|
| Duplicate schema | Same CRD in multiple sources | First source wins; check for conflicts |
| Missing metadata | Conversion bug | Check `crd_to_jsonschema()` |

---

## Evidence

| Claim | Source | Confidence |
|-------|--------|------------|
| Three source types | `sources.yaml`, `scripts/extract.py` | Verified |
| Kubernetes extensions stripped | `scripts/common.py:88-95` | Verified |
| Schema path structure | `scripts/common.py:write_schema()` | Verified |
