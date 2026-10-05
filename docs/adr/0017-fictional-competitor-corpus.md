# ADR-0017: Fully fictional demo corpus, including competitors

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** Planned — Phase 1 (this ADR is updated with measurements when the component is built)
- **Related:** plan §27 (corpus composition), §0.2 A4, §0.2 A5, §23, §24, §35; ADR-0013, ADR-0016; approved deviations D6 and D4 (context)

## Context

MarketSignal is a market-research assistant for consulting-style questions: where to play, how customers perceive a brand, how competitors position themselves. The product spec (§4) asks for a demo corpus of 20–40 sources covering at least 4 source classes, at least 2 structured datasets and at least 1 deck. It names **public competitor documents** as the source of the competitor class.

Three facts constrain the corpus:

1. **The repository is public** (assumption A5). Anything committed is published.
2. **The corpus contains synthetic customer voice**: survey verbatims, interview Q&A, reviews and focus groups. Some of it is negative by design, because contradictions and pain points are planted for evaluation.
3. **Evaluation depends on planted facts.** Gold labels come from a world model whose facts are written into the documents and then frozen against the real ingested corpus (ADR-0013). That only works if every document in the evaluated corpus was generated from the world model.

If real competitors were mixed with synthetic customer voice, the repository would publish invented complaints and claims about real companies. Real filings also carry licensing terms, change over time, and contain facts the world model does not know about, which would break gold-label integrity.

## Decision

- **The whole demo corpus is synthetic and fictional, including the competitors** (A4). The world model (`seed_data/world_model.yaml`) defines three fictional competitors, *Vantage Athletic*, *Kinetic Lab* and *Pace & Co.*, with their positioning, alongside segments, pain points, metrics, planted contradictions, superseded values and gaps.
- **Composition (§27).** The fictional client workspace, Northstar, has about 26 sources:

  | Class | Sources |
  |---|---|
  | Internal | brand strategy PDF; Q3 strategy review PPTX; product performance XLSX; channel performance CSV; FY plan memo MD |
  | Customer | survey CSV (~600 respondents with verbatims); interviews DOCX (12, Q&A); reviews CSV (~800); Gen Z focus-group DOCX; support-themes PDF |
  | Competitor | 3 fictional competitors × {positioning/web snapshot MD or PDF, investor deck PPTX or annual-report excerpt PDF} |
  | Market | Gen Z athletic trends PDF (v1 and v2, superseded); personalization willingness-to-pay study PDF; category sizing XLSX; channel-shift note MD |
  | Planted | 2 injection carriers (a review row and a competitor page); contradiction pairs |

  A decoy workspace, *Southpeak Outdoor* (6 documents with canary facts), exercises isolation (§23). An empty Sandbox workspace takes visitor uploads.
- **Generation.** Template generators render every format from the world model, and a fact ledger records each fact's source, anchor and surface forms. Seeding goes through the real upload API, so seeding also exercises ingestion.
- **Real public filings are an optional add-on.** `scripts/fetch_public_filings` (optional) downloads them locally. **Fetched files are never committed**, are not part of the seeded demo, and are not used by the gold set or CI gates.

## Approved spec deviation

- **Spec position:** the competitor class uses *public competitor documents*.
- **Approved change (D6):** use fictional competitors. An optional script fetches real public filings, which are not committed.
- **Rationale recorded with the approval:** synthetic customer voice that criticizes real brands would be a fabricated claim about real companies. Fictional data also avoids licensing issues and keeps the demo deterministic.
- **Approval requirement:** none was attached beyond the change itself. The script stays optional and its output stays out of the repository.
- **Approved 2026-10-05.**

## Alternatives considered

- **Real competitor documents committed to the repository (the spec's position).** This is the most realistic option. It was rejected because it would place fabricated negative customer voice next to real brand names in a public repo, carry redistribution and licensing risk, and add facts the world model does not know, which breaks gold integrity.
- **Real competitor documents with no synthetic customer voice about competitors.** This removes the defamation-style risk, but it still has the licensing and determinism problems. It also removes the competitor-perception questions that Brand Strategy and cross-class demos depend on.
- **Real names but synthetic content.** Rejected: this is still a fabricated claim about a real company, which is exactly the harm D6 avoids.
- **Real filings fetched at seed time, by default.** This keeps them out of git, but the demo would depend on the network and on third-party document changes, and the gold set could not be frozen reproducibly.

## Tradeoffs accepted

- **Less realism.** Fictional competitor documents are cleaner and shorter than real filings, so parser robustness on messy real-world PDFs is not proven by the seeded demo. The optional script is the way to exercise it manually.
- **Circularity risk.** When one world model generates both documents and questions, the corpus can be too easy (§35). The mitigations, owned by ADR-0013, are: questions written from the fact record without seeing the rendered text; per-item lexical-overlap hardness bins; distractors; a grouped dev/test split; and a fresh-seed holdout with new names, numbers and template variants.
- **Interviewer perception.** A reviewer may ask "does it work on real data?". The answer is the optional real-filings path, plus the Sandbox upload flow on the deployed demo.

## Consequences

**Positive**
- The public repository holds no third-party copyrighted documents and no invented claims about real companies.
- The demo and evaluation are deterministic: the same seed produces the same corpus, the same frozen gold set and the same handles.
- Planted contradictions, superseded values (trends v1 → v2), injection carriers and canaries are known by construction, so behavioural metrics can be scored without guessing.

**Negative**
- The generator and world model are code that must be maintained along with the parsers.
- Metrics on the synthetic corpus do not transfer directly to real corpora. EVALUATION.md must say so.

**Follow-ups**
- Write fetched filings to a git-ignored directory, and extend the CI path check (which already rejects reference-material path patterns and files over 5 MB) to reject that directory.
- README: state that the corpus is synthetic-only and that all company names are fictional (§24 vendor-posture note).
- Any real-filings run is reported separately and never mixed into gated metrics.

**Verification**
- Phase 1 exit: the seeded corpus ingests through the API, and a planted fact is found by lexical **and** dense search and resolves to exact text with its locator.
- Corpus checks: at least 4 classes, at least 2 structured datasets and at least 1 deck present after seeding.
- Gold integrity CI (§27): every `satisfied_by` handle resolves and contains its anchor or surface form, each anchor matches exactly one active parent, and the corpus sha256 matches the manifest.
- Isolation behavioural eval: zero Southpeak canaries in Northstar answers, and the reverse.
- Repository hygiene: gitleaks and the size and path checks pass on every PR, and no fetched filing appears in git history.
