# Contributing to VaultLedger

Thank you for helping improve VaultLedger. Contributions should preserve the project's
local-first privacy boundary, citation traceability, and evidence-led evaluation discipline.

## Before you start

- Read [docs/getting-started.md](docs/getting-started.md) for setup.
- Read [docs/architecture.md](docs/architecture.md) before changing a pipeline boundary.
- Read [docs/evaluation.md](docs/evaluation.md) before changing metrics or generated reports.
- Search existing issues before opening a new one.

Use synthetic documents and synthetic identifiers in issues, tests, screenshots, and
reproduction cases. Never attach real financial documents, extracted user text, local
indexes, traces, or credentials.

## Development workflow

1. Fork the repository and create a focused branch.
2. Keep changes small and update documentation when behavior or setup changes.
3. Add or update tests for behavior changes.
4. Run the relevant checks described in [docs/getting-started.md](docs/getting-started.md).
5. Open a pull request that explains the problem, the change, and any measured result.

Do not hand-edit generated reports. Regenerate them with their documented command and
commit the underlying manifest or receipt that makes the result reproducible.

Dependabot checks Python packages and GitHub Actions weekly. Keep an automated update
focused on dependency changes, preserve intentional compatibility caps from
`pyproject.toml`, and explain any deferred major upgrade in the pull request.

## Evidence and claims

- Do not invent or extrapolate evaluation results.
- Include the population and denominator with every metric.
- Label a reasoned estimate as an estimate.
- Preserve failed and null experiments when they inform a decision.
- Use an Architecture Decision Record for changes that alter a documented invariant.

## Licensing

By submitting a contribution, you agree that it may be licensed under the
[Apache License 2.0](LICENSE). Contributions must be your own work or material you are
authorized to submit. Identify third-party code or assets and their licenses in the pull
request.

## Conduct and security

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md). Report security
issues privately as described in [SECURITY.md](SECURITY.md), not in a public issue.
