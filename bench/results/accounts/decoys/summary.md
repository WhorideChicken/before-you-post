# Account LeakBench (2026-10-28, standard mode)

5 staged accounts of 3 photos plus 4 everyday posts each (7 photos, attacked one by one and linked), 0 errors. In each, one photo shows a first name, one a kind of job or routine, one a town: harmless alone, identifying together. A combination is broken when at least one of its legible pieces is gone from the final photos, as read by a separate transcription pass.

| | One photo at a time | As one account |
|---|---|---|
| Combinations broken | 1/5 | 4/5 |
| Edits made | 1 | 5 |
| Photos changed | 1/15 | 5/35 |
| Share of each photo changed (mean) | 0.2% | 0.3% |
| Time per account (mean, the three single runs in parallel) | 32 s | 67 s |

Whole run cost (estimate, including the verifier): $1.20

## Per account

| Account | Pieces legible | Worst exposure, each photo alone | Worst exposure together | One at a time | As one account |
|---|---|---|---|---|---|
| mina | 2/2 | [1, 1, 2] | 2 | intact, 0 edit(s): - | intact, 0 edit(s): - |
| daniel | 3/3 | [1, 2, 2] | 3 | intact, 0 edit(s): - | broken, 1 edit(s): replace:wooden welcome sign |
| yuna | 3/3 | [1, 1, 2] | 3 | intact, 0 edit(s): - | broken, 2 edit(s): replace:chocolate message plaque, replace:metal water bottle |
| leo | 3/3 | [1, 0, 2] | 3 | intact, 0 edit(s): - | broken, 1 edit(s): replace:transit card |
| priya | 3/3 | [1, 1, 3] | 3 | broken, 1 edit(s): replace:ferry ticket stub | broken, 1 edit(s): replace:ferry ticket |
