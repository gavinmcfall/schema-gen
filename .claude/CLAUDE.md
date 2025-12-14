# k8s-schemas.io Repository Context

Kubernetes CRD JSON Schema extraction and publishing system.

## Read First

1. **@docs/ai-context/ARCHITECTURE.md** - Extraction pipeline and deployment
2. **@docs/ai-context/DOMAIN.md** - Source types and schema format
3. **@docs/ai-context/CONVENTIONS.md** - Coding standards

## Documentation

- @docs/ai-context/ARCHITECTURE.md - Pipeline, deployment, key patterns
- @docs/ai-context/DOMAIN.md - Source types, schema format, business rules
- @docs/ai-context/WORKFLOWS.md - Adding sources, testing, deployment
- @docs/ai-context/CONVENTIONS.md - Code style, naming, commits

## Critical Invariants

### Capsule: ExtractionPipeline

**Invariant**: CRDs are fetched from sources, converted to JSON Schema, enriched with provenance metadata, and published.

### Capsule: SourceTypes

**Invariant**: Four source types: `helm`, `kustomize`, `github`, `url`. Each has a directory under `sources/` with type-specific files.

### Capsule: ProvenanceMetadata

**Invariant**: Every schema includes `x-kubernetes-schema-metadata` with source name, version, and extraction timestamp.

## Quick Reference

| Task | Command |
|------|---------|
| Extract all | `python scripts/extract.py --sources-dir sources --output schemas/` |
| Extract one | `python scripts/extract.py --source flux --sources-dir sources --output schemas/` |
| Run tests | `pytest tests/` |
| Generate index | `python scripts/generate_index.py --schemas-dir schemas/ --output schemas/schemas-index.json` |

## Directory Structure

```
scripts/              # Extraction and generation scripts
sources/
├── helm/             # Helm sources (helmrelease.yaml)
├── kustomize/        # Kustomize sources (kustomization.yaml)
├── github/           # GitHub sources (source.yaml)
└── url/              # URL sources (source.yaml)
schemas/              # OUTPUT - Extracted JSON schemas
public/               # Web interface
tests/                # Test suite
```

## Non-Obvious Truths

- **Kubernetes extensions stripped**: `x-kubernetes-*` fields are removed during conversion
- **Schema paths lowercase**: `GitRepository` becomes `gitrepository.json`
- **Version placeholder**: URL sources use `{version}` which is substituted
- **First source wins**: If multiple sources provide the same CRD, first encountered wins
- **Renovate-native**: Directory structure supports native Renovate managers

## Source Type Selection

| CRD Location | Use Type | File |
|--------------|----------|------|
| Helm chart with `--include-crds` | `helm` | `helmrelease.yaml` |
| GitHub repo path | `kustomize` | `kustomization.yaml` |
| GitHub release asset | `github` | `source.yaml` |
| Direct download URL | `url` | `source.yaml` |
