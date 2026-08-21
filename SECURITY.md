# Security Policy

VaultLedger is a local-first document extraction and question-answering project. It is not
a production financial service and does not provide financial advice.

## Supported versions

Security fixes are applied to the latest commit on `main` and, when practical, the latest
published release. Older revisions are not maintained separately.

## Reporting a vulnerability

Report vulnerabilities through GitHub's
[private vulnerability reporting form](https://github.com/Cent-Capital/VaultLedger/security/advisories/new).
Do not open a public issue for an undisclosed vulnerability.

Include:

- the affected version or commit;
- a concise description of the impact;
- minimal reproduction steps using synthetic data;
- any proposed mitigation.

Never include real financial documents, user questions, extracted text, indexes, traces,
credentials, or other private data in a report. Maintainers will coordinate remediation and
disclosure through the private advisory.

## Security boundaries

- User documents and their derived indexes, graphs, projections, and traces must remain
  outside the repository.
- Local mode uses local Ollama endpoints. The shipped product has no hosted generation tier.
- OCR output can contain incorrect digits or table geometry and must be checked against the
  source document.
- Verified citations establish that a snippet exists; they do not prove that the snippet
  logically supports every generated claim.

These boundaries are documented in greater detail in [docs/limitations.md](docs/limitations.md).
