# MarketSignal seed corpus

Fictional data created for the MarketSignal demo. Every company, person, product, number and quote in this directory is invented. Northstar Athletics, Vantage Athletic, Kinetic Lab, Pace & Co., Southpeak Outdoor and every research firm named in the documents are fictional. No real brands are used.

## What it is

A deterministic, multi-format synthetic corpus for the MarketSignal strategy-research demo (see docs/PRODUCT_SPEC.md section 4 and docs/ARCHITECTURE_PLAN.md section 27). `world_model.yaml` is the single source of truth: workspaces, segments, pain-point prevalence, competitor positioning, product / channel / category metrics, evidence for and against the personalization hypothesis, planted contradictions, superseded values, distractors, Southpeak canary facts, injection carriers and the fact list. Documents are rendered from it by templates in `generator/` (no LLM calls at generation time).

- `world_model.yaml` - world model and fact definitions
- `generator/` - `generate.py` (renders everything), `render.py` (PDF/DOCX/PPTX/MD/TXT/CSV/XLSX + `normalize_zip`), `tabular.py` (seeded tables), `text_pools.py`, `content/*.py` (document text with `{F:<fact_id>}` anchor placeholders), `content_check.py`, `verify.py`
- `generated/` - the rendered uploads plus `manifest.json` (upload order, sha256)
- `fact_ledger.json` - every planted fact with anchor and surface forms (basis for gold sets)

## Regenerate and check

Run from the repository root with the backend virtualenv:

```
uv --directory backend run python ../seed_data/generator/generate.py           # regenerate in place
uv --directory backend run python ../seed_data/generator/generate.py --check   # byte-identical check (exit 1 on mismatch)
uv --directory backend run python ../seed_data/generator/verify.py             # full self-verification
```

Determinism: reportlab runs with `invariant=1`; DOCX/PPTX/XLSX get fixed core-property dates and every zip is rewritten by `normalize_zip` (fixed 2026-01-01 timestamps, fixed entry order, deflate level 6); all randomness uses `random.Random` seeded from `meta.seed` (20260101).

## Conventions

- Plain ASCII text everywhere; every document carries the visible line "Fictional data created for the MarketSignal demo." (PDF footers: "Fictional data created for the MarketSignal demo - page N"; CSV/XLSX: a `data_notice` column).
- PDF: Helvetica 10.5pt body, 14-18pt Helvetica-Bold headings on their own line, "- " bullets, tables as text rows.
- DOCX: built-in Title, Heading 1, Heading 2, Normal, List Bullet styles; interviews use Heading 1 sections ("Interview N - Name X., age, city (fictional)") with "Q: " / "A: " paragraphs.
- PPTX: title placeholder per slide, one bullet text frame, optional table, speaker notes via notes_slide.
- Markdown: ATX headings, paragraphs, "- " bullets. TXT: no markup, blank-line separated paragraphs.
- CSV: comma-delimited, RFC 4180 quoting, CRLF line endings, header in row 1; `Northstar_Customer_Survey_2026.csv` is UTF-8 with BOM. In the channel CSV `sessions` means store visits for Stores.
- XLSX: header in row 1, data from row 2, numeric cells typed as numbers, no merged cells.
- Fact anchors: sentence anchors occur verbatim exactly once per workspace after whitespace normalisation, inside a single paragraph / answer / slide text frame / notes block / table cell; row anchors identify exactly one row.
- Planted prompt-injection carriers (review RV-00577 and the Kinetic Lab web snapshot) are test data and must never be obeyed; canary outputs are listed in the ledger.
- Source codes are unique per workspace; GENZ-TRENDS has version 1 (2025) and version 2 (2026) which supersedes it.

## Counts

- Northstar core facts: 92 (csv 10, docx 16, markdown 10, pdf 29, pptx 13, text 3, xlsx 11)
- Distractors: 10; superseded: 4; contradiction pairs: 5; Southpeak canaries: 7; injection carriers: 2

## Files

| # | Workspace | Source code | v | Class | Type | File | Bytes | sha256 (prefix) |
|---|---|---|---|---|---|---|---|---|
| 1 | NORTHSTAR | BRAND-STRATEGY | 1 | internal | pdf | `northstar/Northstar_Brand_Strategy_2026.pdf` | 18266 | `9de94a90655b` |
| 2 | NORTHSTAR | Q3-REVIEW | 1 | internal | pptx | `northstar/Northstar_Q3_Strategy_Review.pptx` | 63022 | `344f554d6753` |
| 3 | NORTHSTAR | PRODUCT-PERF | 1 | internal | xlsx | `northstar/Northstar_Product_Performance.xlsx` | 22536 | `3619f10888f3` |
| 4 | NORTHSTAR | CHANNEL-PERF | 1 | internal | csv | `northstar/Northstar_Channel_Performance.csv` | 16113 | `59c8fe1dc951` |
| 5 | NORTHSTAR | FY27-MEMO | 1 | internal | markdown | `northstar/Northstar_FY27_Planning_Memo.md` | 6446 | `d52231b6bef0` |
| 6 | NORTHSTAR | PERSO-PILOT | 1 | internal | docx | `northstar/Northstar_Personalization_Pilot_Results.docx` | 41499 | `7da49b95c70d` |
| 7 | NORTHSTAR | FIN-SUMMARY-FY26 | 1 | financial | xlsx | `northstar/Northstar_Financial_Summary_FY26.xlsx` | 6483 | `702d01f753df` |
| 8 | NORTHSTAR | SURVEY-2026 | 1 | customer | csv | `northstar/Northstar_Customer_Survey_2026.csv` | 167215 | `90a83a8c612d` |
| 9 | NORTHSTAR | INTERVIEWS | 1 | customer | docx | `northstar/Northstar_Customer_Interviews.docx` | 43400 | `ce1461eb6047` |
| 10 | NORTHSTAR | REVIEWS | 1 | customer | csv | `northstar/Northstar_Product_Reviews.csv` | 188263 | `afee638f58af` |
| 11 | NORTHSTAR | GENZ-FOCUS-GROUP | 1 | customer | docx | `northstar/Northstar_GenZ_Focus_Group.docx` | 40332 | `50fa0e522a71` |
| 12 | NORTHSTAR | SUPPORT-THEMES | 1 | customer | pdf | `northstar/Northstar_Support_Themes_Q3.pdf` | 9790 | `b2786a807d56` |
| 13 | NORTHSTAR | ANALYST-CALL | 1 | customer | text | `northstar/Northstar_Analyst_Call_Notes.txt` | 6168 | `ef8d48b64e91` |
| 14 | NORTHSTAR | VANTAGE-WEB | 1 | competitor | markdown | `northstar/Vantage_Athletic_Positioning.md` | 5163 | `ba07f7bd3193` |
| 15 | NORTHSTAR | VANTAGE-DECK | 1 | competitor | pptx | `northstar/Vantage_Athletic_Investor_Deck.pptx` | 53513 | `35160733d8c7` |
| 16 | NORTHSTAR | KINETIC-WEB | 1 | competitor | markdown | `northstar/Kinetic_Lab_Positioning.md` | 4364 | `382ea77aed15` |
| 17 | NORTHSTAR | KINETIC-AR | 1 | competitor | pdf | `northstar/Kinetic_Lab_Annual_Report_Excerpt.pdf` | 10371 | `1a2d315ccbe0` |
| 18 | NORTHSTAR | PACE-WEB | 1 | competitor | markdown | `northstar/Pace_Co_Positioning.md` | 3902 | `305cf35379ef` |
| 19 | NORTHSTAR | PACE-DECK | 1 | competitor | pptx | `northstar/Pace_Co_Investor_Deck.pptx` | 53347 | `9c7c843711f0` |
| 20 | NORTHSTAR | GENZ-TRENDS | 1 | market | pdf | `northstar/GenZ_Athletic_Trends_2025.pdf` | 12318 | `441d6c5bbea4` |
| 21 | NORTHSTAR | GENZ-TRENDS | 2 | market | pdf | `northstar/GenZ_Athletic_Trends_2026.pdf` | 12382 | `dd97fe96fabe` |
| 22 | NORTHSTAR | WTP-STUDY | 1 | market | pdf | `northstar/Personalization_WTP_Study.pdf` | 11027 | `63cd328d4e37` |
| 23 | NORTHSTAR | CATEGORY-SIZING | 1 | market | xlsx | `northstar/Athletic_Category_Sizing.xlsx` | 7785 | `9dfe65b1ce48` |
| 24 | NORTHSTAR | CHANNEL-SHIFT | 1 | market | markdown | `northstar/Retail_Channel_Shift_Note.md` | 5080 | `fc9b63b855e8` |
| 1 | SOUTHPEAK | BRAND-STRATEGY | 1 | internal | pdf | `southpeak/Southpeak_Brand_Strategy.pdf` | 10593 | `8dec552efade` |
| 2 | SOUTHPEAK | SURVEY-2026 | 1 | customer | csv | `southpeak/Southpeak_Customer_Survey.csv` | 63884 | `03d9cd65a091` |
| 3 | SOUTHPEAK | INTERVIEWS | 1 | customer | docx | `southpeak/Southpeak_Interviews.docx` | 40902 | `84ec51bc4e61` |
| 4 | SOUTHPEAK | BOARD-DECK | 1 | internal | pptx | `southpeak/Southpeak_Board_Deck.pptx` | 56314 | `f0d5e6f4795a` |
| 5 | SOUTHPEAK | CHANNEL-DATA | 1 | internal | xlsx | `southpeak/Southpeak_Channel_Data.xlsx` | 9095 | `68013d938af1` |
| 6 | SOUTHPEAK | PLANNING-NOTES | 1 | internal | markdown | `southpeak/Southpeak_Notes.md` | 4684 | `bb8f4bd81edb` |
