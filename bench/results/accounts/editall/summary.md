# Account LeakBench (2026-10-28, standard mode)

5 staged accounts of 3 photos, 0 errors. In each, one photo shows a first name, one a kind of job or routine, one a town: harmless alone, identifying together. A combination is broken when at least one of its legible pieces is gone from the final photos, as read by a separate transcription pass.

| | One photo at a time | As one account |
|---|---|---|
| Combinations broken | 2/5 | 5/5 |
| Edits made | 2 | 16 |
| Photos changed | 2/15 | 15/15 |
| Share of each photo changed (mean) | 0.3% | 6.1% |
| Time per account (mean, the three single runs in parallel) | 35 s | 63 s |

Whole run cost (estimate, including the verifier): $0.97

## Per account

| Account | Pieces legible | Worst exposure, each photo alone | Worst exposure together | One at a time | As one account |
|---|---|---|---|---|---|
| mina | 2/2 | [1, 0, 2] | 3 | intact, 0 edit(s): - | broken, 4 edit(s): replace:paper coffee cup, pixelate:science classroom interior, replace:folded newspaper, pixelate:science lab desks |
| daniel | 3/3 | [1, 1, 2] | 3 | intact, 0 edit(s): - | broken, 3 edit(s): replace:birthday cake, replace:firefighter turnout jacket, replace:town welcome sign |
| yuna | 3/3 | [1, 1, 2] | 3 | intact, 0 edit(s): - | broken, 3 edit(s): replace:chocolate message plaque, replace:open notebook, replace:folded yellow t-shirt |
| leo | 3/3 | [1, 0, 3] | 3 | broken, 1 edit(s): replace:plastic transit card | broken, 3 edit(s): replace:guitar case sticker, replace:pinned paper notice, replace:held transit card |
| priya | 3/3 | [1, 1, 3] | 3 | broken, 1 edit(s): replace:ferry paper ticket | broken, 3 edit(s): replace:white coffee mug, replace:paper checklist, erase:ferry ticket |
