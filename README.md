# k8s-schemas.io

A community-maintained registry of Kubernetes CRD JSON schemas for IDE validation.

> **Status:** Under active development

## What is this?

Kubernetes Custom Resource Definitions (CRDs) don't always ship with JSON schemas, making it difficult to validate your manifests in your editor. This project generates and hosts JSON schemas for popular CRDs, so you get autocomplete and validation directly in your IDE.

## Usage

Add a schema reference to the top of your YAML file:

```yaml
# yaml-language-server: $schema=https://k8s-schemas.io/helm.toolkit.fluxcd.io/v2/helmrelease.json
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: my-app
spec:
  # Your IDE now validates this
```

### URL Format

```
https://k8s-schemas.io/{group}/{version}/{kind}.json
```

Examples:
- `https://k8s-schemas.io/helm.toolkit.fluxcd.io/v2/helmrelease.json`
- `https://k8s-schemas.io/cert-manager.io/v1/certificate.json`
- `https://k8s-schemas.io/gateway.networking.k8s.io/v1/gateway.json`

## Supported Editors

Any editor with [yaml-language-server](https://github.com/redhat-developer/yaml-language-server) support:

- VS Code (with YAML extension)
- Neovim (with LSP)
- JetBrains IDEs
- Helix
- And others

## How It Works

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   sources.yaml  │ ──► │  Renovate Bot    │ ──► │  PR with bump   │
│                 │     │  watches sources │     │                 │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ k8s-schemas.io  │ ◄── │ Cloudflare Pages │ ◄── │  CI extracts    │
│                 │     │                  │     │  CRD schemas    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

1. **Sources defined** in `sources.yaml` (Helm charts, GitHub releases, etc.)
2. **Renovate watches** for new versions and creates PRs
3. **CI extracts** CRDs and converts them to JSON Schema
4. **Schemas committed** to the `schemas/` directory
5. **Published** to Cloudflare Pages at k8s-schemas.io

## Adding a New CRD Source

Edit `sources.yaml` and add your source:

```yaml
sources:
  # Helm chart
  - name: my-operator
    type: helm
    registry: https://charts.example.com
    chart: my-operator
    version: 1.0.0

  # GitHub release
  - name: another-operator
    type: github
    repo: org/another-operator
    version: v2.0.0
    assets:
      - crds.yaml

  # Direct URL
  - name: some-crd
    type: url
    url: https://example.com/crds/{version}/crd.yaml
    version: v1.0.0
```

Then run locally to test:

```bash
pip install pyyaml requests
python scripts/extract.py --source my-operator --output schemas/
```

## Local Development

```bash
# Clone the repo
git clone https://github.com/gavinmcfall/schema-gen.git
cd schema-gen

# Install dependencies
pip install pyyaml requests

# Extract a specific source
python scripts/extract.py --source flux --output schemas/

# Extract all sources
python scripts/extract.py --all --output schemas/
```

## Project Structure

```
schema-gen/
├── .github/
│   └── workflows/
│       ├── extract.yaml    # Extracts CRDs on source changes
│       └── publish.yaml    # Publishes to Cloudflare Pages
├── scripts/
│   ├── extract.py          # Main extraction script
│   └── detect_changes.py   # Detects changed sources for CI
├── schemas/                # Generated JSON schemas (committed)
│   └── {group}/
│       └── {version}/
│           └── {kind}.json
├── sources.yaml            # Source definitions
├── renovate.json           # Renovate configuration
└── README.md
```

## Contributing

Contributions welcome! The main ways to contribute:

1. **Add new CRD sources** - Edit `sources.yaml`
2. **Improve extraction** - Enhance `scripts/extract.py`
3. **Report issues** - Schema bugs, missing CRDs, etc.

## Acknowledgements

- [datreeio/CRDs-catalog](https://github.com/datreeio/CRDs-catalog) - Inspiration and crd-extractor tooling
- [kubesearch.dev](https://kubesearch.dev) - Community deployment discovery
- [home-operations](https://github.com/home-operations) - Community support

## License

Apache 2.0 - see [LICENSE](LICENSE) for details.
