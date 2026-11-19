# Work inventory and GitHub contribution split

## What was already present before this integration

The uploaded team baseline already contained:
- `main.py`: CLI argument handling, loading, event execution, and CSV export orchestration.
- `src/models.py`: domain dataclasses and Decimal quantization.
- `src/parser.py`: product/coupon/member/parameter loaders and command parsing.
- `src/engine.py`: billing, discounts, GST, loyalty, returns, and Z-report logic.
- `src/formatter.py`: invoice, return voucher, Z-report, and evaluation CSV formatting.
- `tests/test_pos_engine.py`: 23 tests for BR-01–BR-13 and the eight edge cases.
- `docs/DESIGN.md` and `docs/DECISION_LOG.md`: design and decision records.
- Earlier sample invoice, return, and Z-report text files.

These files are retained in `previous_work/` as an unmodified snapshot. The project authorship metadata names both Aditi Anshu and Aditi Chaudhary. The uploaded material does not provide a reliable file-by-file author map, so individual ownership of the baseline should be confirmed from Git commit history/team records rather than guessed.

## Integration and completion work added in this assembled folder

The runnable top-level project includes:
1. Correct Python package layout under `src/`, matching imports used by `main.py` and tests.
2. The complete supplied data pack in `data/` (the original uploaded CSV/TXT contents are retained).
3. Loading of `offers.csv` and passing offer definitions into the engine, including validity dates, buy/free quantities, and per-bill free-item caps.
4. Minimum net-weight rejection as an explicit event-level validation error; the CLI records the event error and continues without creating a bill line.
5. A Z-report `total_refunds` compatibility property used by the existing test suite.
6. Return handling for a partial return of identical-SKU multi-buy units, including a free-item clawback when the remaining quantity no longer supports all free units.
7. Updated tests to assert the data-pack contract: rejected returns are represented as `REJECTED` rows rather than thrown away as exceptions.
8. A full data-pack integration test.
9. The completed generated output set and this run guide.

## Suggested GitHub contribution split

Use real commits under the account of the person who performed each change. A clean way to separate work is:

| Commit / PR | What to include | Attribution |
|---|---|---|
| 1. `baseline: add original POS engine and design` | Original `main.py`, `src/`, original unit tests, design and decision log | Existing team work; split names only after checking commit history |
| 2. `data: add PS-047 evaluation data pack` | `data/*.csv`, `data/commands.txt`, data dictionary | Person who added the supplied data files |
| 3. `fix: integrate offer definitions and edge-case handling` | Current parser/engine/models changes | Person(s) who implemented and reviewed these specific changes |
| 4. `test: add full data-pack integration coverage` | `tests/test_data_pack_integration.py` and relevant test updates | Actual test author |
| 5. `docs: add execution guide and contribution inventory` | `README.md`, `docs/WORK_SPLIT.md` | Actual documentation author |
| 6. `output: add generated evaluation artifacts` | `output/` if your instructor expects checked-in outputs | Person who ran and validated the project |

### Important attribution note

Do not label all pre-existing files as Aditi Anshu's work or all new files as Aditi Chaudhary's work unless that is factually correct. Use `git log --follow -- path/to/file`, GitHub commit history, and your team's actual division of tasks to establish authorship. If both worked on a file, record it as joint work.

## What you should upload to GitHub

Upload the complete project root:
- `main.py`
- `src/`
- `data/`
- `tests/`
- `docs/`
- `README.md`
- `.gitignore`
- `output/` only if generated output submission is required
- `previous_work/` if you want the preserved baseline and audit trail included in the repository

Before pushing, confirm that `previous_work/` is acceptable to your instructor; it is useful for transparency but can be omitted from the final deployment branch if repository size or submission rules require a lean project.
