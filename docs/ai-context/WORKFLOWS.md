---
description: Operational workflows for adding sources, running extraction, and deployment
tags: ["AddingSource", "Extraction", "Deployment", "Testing"]
audience: ["LLMs", "Humans"]
---

# Workflows

## Adding a New Source

### 1. Determine Source Type

| If CRDs are in... | Use type | Directory | File |
|-------------------|----------|-----------|------|
| Helm chart | `helm` | `sources/helm/<name>/` | `helmrelease.yaml` |
| GitHub repo path | `kustomize` | `sources/kustomize/<name>/` | `kustomization.yaml` |
| GitHub release asset | `github` | `sources/github/<name>/` | `source.yaml` |
| Predictable URL | `url` | `sources/url/<name>/` | `source.yaml` |

### 2. Find the CRD Location

**For Helm charts**:
```bash
# Search for chart
helm search repo <name>

# Check if chart includes CRDs
helm template <chart> --include-crds 2>/dev/null | grep "kind: CustomResourceDefinition"
```

**For GitHub repos (kustomize)**:
```bash
# Look for CRD directories in the repo
# Common paths: config/crd/bases/, deploy/crds/, charts/*/crds/
gh api repos/<owner>/<repo>/contents/config/crd/bases --jq '.[].name'
```

**For GitHub releases**:
```bash
# List release assets
gh release view <version> --repo <owner/repo> --json assets --jq '.assets[].name'

# Common asset names: install.yaml, crds.yaml, *-operator.yaml
```

**For URLs**:
- Check project documentation for CRD installation instructions
- Look for patterns like `kubectl apply -f https://...`

### 3. Create Source Directory and File

**Helm source** (`sources/helm/<name>/helmrelease.yaml`):
```yaml
repository: https://charts.example.com
chart: my-operator
version: 1.0.0
```

**Kustomize source** (`sources/kustomize/<name>/kustomization.yaml`):
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- https://github.com/org/repo//path/to/crds?ref=v1.0.0
```

**GitHub source** (`sources/github/<name>/source.yaml`):
```yaml
# renovate: datasource=github-releases depName=org/repo
repository: org/repo
version: v1.0.0
assets:
- install.yaml
- crds.yaml
```

**URL source** (`sources/url/<name>/source.yaml`):
```yaml
# renovate: datasource=github-releases depName=org/repo versioning=semver
urls:
- https://example.com/releases/{version}/crds.yaml
version: v1.0.0
```

### 4. Test Extraction

```bash
# Extract single source
python scripts/extract.py --source my-operator --sources-dir sources --output /tmp/test-schemas/

# Verify output
ls -la /tmp/test-schemas/
```

### 5. Run Tests

```bash
pytest tests/ -v
```

### 6. Commit

```bash
git add sources/helm/my-operator/
git commit -m "feat(sources): add my-operator CRDs"
git push
```

---

## Running Full Extraction

### Local

```bash
# All sources
python scripts/extract.py --sources-dir sources --output schemas/

# Single source
python scripts/extract.py --source flux --sources-dir sources --output schemas/

# With verbose output
python scripts/extract.py --source flux --sources-dir sources --output schemas/ --verbose
```

### CI

Extraction runs automatically when:
- `sources/**` changes (any source directory)
- Scripts change
- Workflow dispatch (manual trigger)

---

## Updating a Source Version

### Automatic (Renovate)

Sources use native Renovate managers where possible:

| Source Type | Renovate Manager |
|-------------|------------------|
| `helm` | `helm-values` manager (parses helmrelease.yaml) |
| `kustomize` | `kustomize` manager (parses kustomization.yaml) |
| `github` | `regex` manager (uses `# renovate:` comment) |
| `url` | `regex` manager (uses `# renovate:` comment) |

Renovate will automatically create PRs when new versions are available.

### Manual

**1. Find New Version**:
```bash
# For Helm
helm repo update
helm search repo <chart> --versions | head -5

# For GitHub
gh release list --repo <owner/repo> --limit 5
```

**2. Update the source file**:

For Helm (`sources/helm/flux/helmrelease.yaml`):
```yaml
repository: oci://ghcr.io/fluxcd-community/charts
chart: flux2
version: 2.15.0  # Updated from 2.14.1
```

For Kustomize (`sources/kustomize/cilium/kustomization.yaml`):
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- https://github.com/cilium/cilium//pkg/k8s/apis/cilium.io/client/crds?ref=v1.17.1  # Updated
```

**3. Test and Commit**:
```bash
python scripts/extract.py --source flux --sources-dir sources --output /tmp/test/
git add sources/helm/flux/
git commit -m "chore(sources): update flux to 2.15.0"
git push
```

---

## Deployment

### Automatic

Deployment happens automatically when:
- `schemas/**` changes (extraction output)
- `public/**` changes (web interface)
- `scripts/generate_index.py` changes

### Manual

```bash
# Trigger via GitHub Actions UI
# Or push a change to trigger path filters
```

### Verify

```bash
# Check deployment status
gh run list --workflow=publish.yaml --limit 3

# Test the site
curl -sI https://k8s-schemas.nerdz.cloud | head -5

# Check schema index
curl -s https://k8s-schemas.nerdz.cloud/schemas-index.json | jq '.stats'
```

---

## Testing

### Run All Tests

```bash
pytest tests/ -v
```

### Run Specific Tests

```bash
# Unit tests only
pytest tests/test_common.py -v

# Integration tests only
pytest tests/test_extract.py -v

# Single test
pytest tests/test_common.py::TestSchemaConversion::test_crd_to_jsonschema_v1 -v
```

### Test Coverage

```bash
pytest tests/ --cov=scripts --cov-report=html
open htmlcov/index.html
```

---

## Troubleshooting

### Extraction Fails

**Check source availability**:
```bash
# Helm
helm repo update
helm show chart <repo>/<chart> --version <version>

# GitHub
gh release view <version> --repo <owner/repo>

# URL
curl -sI "<url>"
```

**Common issues**:
- Version doesn't exist
- Asset renamed in new release
- Chart moved to different repo

### Zero CRDs Extracted

**Causes**:
- CRDs are in a separate chart (e.g., `*-crds` chart)
- CRDs are installed via `kubectl apply` not Helm
- File contains other resources, not CRDs

**Debug**:
```bash
# Check what's in the file
helm template <chart> --include-crds 2>/dev/null | grep "^kind:"
```

### Schema Validation Errors

**Check the generated schema**:
```bash
cat schemas/<group>/<version>/<kind>.json | jq '.properties | keys'
```

**Common issues**:
- Kubernetes extensions not stripped
- Invalid JSON Schema syntax in source CRD

---

## Command Reference

| Command | Purpose |
|---------|---------|
| `python scripts/extract.py --sources-dir sources --output schemas/` | Extract all sources |
| `python scripts/extract.py --source X --sources-dir sources --output Y` | Extract single source |
| `python scripts/generate_index.py --schemas-dir D --output F` | Generate web index |
| `pytest tests/` | Run test suite |
| `gh run list --workflow=publish.yaml` | Check deployment status |
