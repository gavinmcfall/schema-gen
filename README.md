# k8s-schemas

A single source of truth for Kubernetes CRD JSON schemas, enabling IDE validation for your YAML manifests.

> ⚠️ **Under Development** — This project is not yet ready for use.

## What is this?

Kubernetes Custom Resource Definitions (CRDs) don't always ship with JSON schemas, making it difficult to validate your manifests in your editor. This project generates and hosts JSON schemas for popular CRDs, so you get autocomplete and validation directly in your IDE.

## Usage

Add a schema reference to the top of your YAML file:

```yaml
# yaml-language-server: $schema=https://k8s-schemas.io/helm.toolkit.fluxcd.io/helmrelease_v2.json
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: my-app
spec:
  # Your IDE now validates this ✓
```

That's it. No downloads, no local tooling — just add the comment and your editor handles the rest.

## Supported Editors

Any editor with [yaml-language-server](https://github.com/redhat-developer/yaml-language-server) support:

- VS Code (with YAML extension)
- Neovim (with LSP)
- JetBrains IDEs
- And others

## How It Works

Schemas are automatically generated from upstream CRD definitions in their source repositories. No cluster access required.

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
