# TODO - k8s-schemas.io Improvements

## High Priority

### Renovate Configuration

Sources now use native Renovate managers. Configure Renovate for this repository.

**Requirements**:
- [ ] Enable Renovate on the repository
- [ ] Configure `helm-values` manager for `sources/helm/**/helmrelease.yaml`
- [ ] Configure `kustomize` manager for `sources/kustomize/**/kustomization.yaml`
- [ ] Configure `regex` manager for `sources/github/**/source.yaml` and `sources/url/**/source.yaml`
- [ ] Set up automerge for patch updates (optional)
- [ ] Set up PR grouping for related updates

**Implementation**: Add `renovate.json`:
```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:base"],
  "enabledManagers": ["helm-values", "kustomize", "regex"]
}
```

---

### OCI Registry Support

Some projects publish Helm charts to OCI registries instead of traditional Helm repos. The current `helm` source type already supports OCI registries via the `oci://` prefix.

**Example** (`sources/helm/cilium/helmrelease.yaml`):
```yaml
repository: oci://quay.io/cilium/charts
chart: cilium
version: 1.16.0
```

**Remaining work**:
- [ ] Test OCI authentication for private registries
- [ ] Document OCI-specific configuration

---

## Medium Priority

### Schema Deduplication

Multiple sources may provide the same CRD. Currently, first source wins. Consider smarter deduplication.

**Options**:
- [ ] Track all sources for each schema (not just first)
- [ ] Allow explicit priority in sources.yaml
- [ ] Detect and warn on duplicates

---

### Delta Updates

Currently, full extraction runs on any source change. Implement incremental updates.

**Requirements**:
- [ ] Only extract changed sources
- [ ] Preserve unchanged schemas
- [ ] Reduce CI time and API calls

**Current**: `extract.yaml` detects changed sources but still overwrites all schemas.

---

### Web Interface Improvements

- [ ] Add schema preview/viewer (syntax highlighted JSON)
- [ ] Add download button for individual schemas
- [ ] Add bulk download (zip of all schemas)
- [ ] Add dark/light mode toggle
- [ ] Add schema diff view between versions
- [ ] Add RSS/Atom feed for updates

---

### Source Discovery

Help users find sources to add.

- [ ] Script to check if a GitHub repo has CRDs
- [ ] Script to validate a source definition before adding
- [ ] Documentation for common CRD locations

---

## Low Priority

### Metrics and Analytics

- [ ] Track download counts per schema
- [ ] Track search queries on web interface
- [ ] Dashboard for popular schemas

---

### API Endpoint

Currently static files only. Consider adding API.

- [ ] `/api/v1/schemas/{group}/{version}/{kind}` endpoint
- [ ] `/api/v1/search?q=...` endpoint
- [ ] OpenAPI spec for API

**Trade-off**: Adds complexity; static files are simpler and cheaper.

---

### Alternative Schema Formats

- [ ] OpenAPI 3.0 output (for different tooling)
- [ ] TypeScript type definitions
- [ ] Go struct definitions

---

### Schema Validation

- [ ] Validate generated schemas against JSON Schema meta-schema
- [ ] Test schemas against example CRs
- [ ] Report validation errors in CI

---

## Completed

- [x] Basic extraction for helm, github, url sources
- [x] Web interface with search
- [x] Cloudflare Pages deployment
- [x] Provenance metadata
- [x] Test suite
- [x] AI context documentation
- [x] Directory-based source structure for native Renovate support
- [x] Kustomize source type for GitHub repo paths

---

## Contributing

To pick up a TODO item:
1. Create an issue referencing this file
2. Discuss approach if non-trivial
3. Submit PR with implementation and tests
