# AI Assistant Configuration

This repository uses AI coding assistants with shared context from a centralized documentation hub.

## Documentation Location

All AI assistant context is centralized in **[`docs/ai-context/`](docs/ai-context/)**:

- [README.md](docs/ai-context/README.md) - Overview and navigation
- [ARCHITECTURE.md](docs/ai-context/ARCHITECTURE.md) - System architecture and key patterns
- [DOMAIN.md](docs/ai-context/DOMAIN.md) - Business rules and source types
- [WORKFLOWS.md](docs/ai-context/WORKFLOWS.md) - Operational workflows
- [CONVENTIONS.md](docs/ai-context/CONVENTIONS.md) - Coding standards

This centralized approach provides:
- Single source of truth for all AI tools
- No duplication across tool-specific directories
- Easy updates - change once, all tools benefit
- Version controlled and contributor-friendly

## Tool-Specific Configurations

### Claude Code
**Configuration:** [`.claude/CLAUDE.md`](.claude/CLAUDE.md)
- Imports files from `docs/ai-context/` using `@path/to/file.md` syntax

### GitHub Copilot
**Configuration:** [`.github/copilot-instructions.md`](.github/copilot-instructions.md) (if created)
- References files from `docs/ai-context/` via markdown links

## Quick Reference

### What This Project Does

k8s-schemas.io extracts JSON Schemas from Kubernetes CRDs and publishes them for IDE validation. Sources include Helm charts, GitHub releases, and direct URLs.

### Directory Structure

```
schema-gen/
├── docs/
│   └── ai-context/          # AI context documentation
├── .claude/
│   └── CLAUDE.md            # Claude Code configuration
├── scripts/
│   ├── extract.py           # Main extraction script
│   ├── common.py            # Shared utilities
│   ├── generate_index.py    # Web index generator
│   └── detect_changes.py    # CI change detection
├── sources/
│   ├── helm/                # Helm chart sources (helmrelease.yaml)
│   ├── kustomize/           # Kustomize sources (kustomization.yaml)
│   ├── github/              # GitHub release sources (source.yaml)
│   └── url/                 # URL sources (source.yaml)
├── schemas/                 # Extracted JSON schemas (generated)
├── public/
│   └── index.html           # Web interface
├── tests/                   # Test suite
└── .github/workflows/       # CI/CD pipelines
```

### Key Commands

```bash
# Run extraction for all sources
python scripts/extract.py --sources-dir sources --output schemas/

# Run extraction for specific source
python scripts/extract.py --source flux --sources-dir sources --output schemas/

# Run tests
pytest tests/

# Generate schema index
python scripts/generate_index.py --schemas-dir schemas/ --output schemas/schemas-index.json
```

### Source Types

| Type | Directory | File | Description |
|------|-----------|------|-------------|
| `helm` | `sources/helm/<name>/` | `helmrelease.yaml` | Helm chart with CRDs |
| `kustomize` | `sources/kustomize/<name>/` | `kustomization.yaml` | GitHub repo path |
| `github` | `sources/github/<name>/` | `source.yaml` | GitHub release assets |
| `url` | `sources/url/<name>/` | `source.yaml` | Direct URL to CRD YAML |

## Adding New Context

When adding new documentation:

1. Add or update markdown files in [`docs/ai-context/`](docs/ai-context/)
2. Tool-specific configs will automatically see the changes
3. Commit changes to version control

**Do not** create duplicate documentation in tool-specific directories.

## Roadmap

See [TODO.md](TODO.md) for planned improvements including automated version checking and scheduled updates.
