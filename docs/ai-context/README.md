---
description: Navigation hub for k8s-schemas.io AI context documentation
tags: ["Navigation", "DocumentStructure", "AIContext"]
audience: ["LLMs", "Humans"]
---

# AI Context Documentation

This directory contains the single source of truth for AI assistant context.

## Read These First

**New to this repository?** Read in order:

1. **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and extraction pipeline
2. **[DOMAIN.md](DOMAIN.md)** - Source types, schema format, business rules
3. **[CONVENTIONS.md](CONVENTIONS.md)** - Coding standards

**Working on the project?** Also read:

- **[WORKFLOWS.md](WORKFLOWS.md)** - How to add sources, run extraction, deploy

---

## Document Map

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Extraction pipeline, deployment, key patterns |
| [DOMAIN.md](DOMAIN.md) | Source types, schema format, provenance metadata |
| [WORKFLOWS.md](WORKFLOWS.md) | Adding sources, testing, deployment |
| [CONVENTIONS.md](CONVENTIONS.md) | Code style, naming, commit guidelines |

---

## What This Project Does

**k8s-schemas.io** extracts JSON Schemas from Kubernetes Custom Resource Definitions (CRDs) and publishes them for IDE validation.

### The Problem

Kubernetes CRDs define custom resources, but IDEs can't validate YAML against them without JSON Schemas.

### The Solution

1. **Extract** CRDs from Helm charts, GitHub releases, and direct URLs
2. **Convert** OpenAPI schemas embedded in CRDs to JSON Schema
3. **Publish** schemas with provenance metadata to a static site
4. **Serve** via web interface with search and copy-to-clipboard

### Who Uses It

- Developers writing Kubernetes manifests in VS Code, Neovim, etc.
- CI/CD pipelines validating manifests with kubeconform
- Anyone who wants autocomplete and validation for CRDs

---

## Quick Facts

| Fact | Value |
|------|-------|
| Schema count | ~1,450+ |
| Source count | ~125 |
| API groups | ~244 |
| Update frequency | Manual (automated planned) |
| Hosting | Cloudflare Pages |

---

## Success Metrics

Documentation succeeds when:

- Contributors can add a new source in <5 minutes
- AI assistants understand the extraction pipeline
- The project's purpose and structure are clear in <2 minutes of reading
