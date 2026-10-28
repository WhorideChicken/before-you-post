# Account LeakBench (2026-10-28, standard mode)

5 staged accounts of 3 photos, 0 errors. In each, one photo shows a first name, one a kind of job or routine, one a town: harmless alone, identifying together. A combination is broken when at least one of its legible pieces is gone from the final photos, as read by a separate transcription pass.

| | One photo at a time | As one account |
|---|---|---|
| Combinations broken | 1/5 | 4/5 |
| Edits made | 1 | 9 |
| Photos changed | 1/15 | 6/15 |
| Share of each photo changed (mean) | 0.2% | 2.8% |
| Time per account (mean, the three single runs in parallel) | 36 s | 74 s |

Whole run cost (estimate, including the verifier): $0.91

## Per account

| Account | Pieces legible | Worst exposure, each photo alone | Worst exposure together | One at a time | As one account |
|---|---|---|---|---|---|
| mina | 2/2 | [1, 2, 2] | 3 | intact, 0 edit(s): - | intact, 3 edit(s): replace:stack of lab reports, pixelate:lab microscope, replace:classroom wall poster |
| daniel | 3/3 | [1, 1, 2] | 3 | intact, 0 edit(s): - | broken, 3 edit(s): replace:birthday cake, pixelate:birthday cake candles, replace:roadside welcome sign |
| yuna | 3/3 | [1, 1, 2] | 3 | intact, 0 edit(s): - | broken, 1 edit(s): replace:chocolate birthday plaque |
| leo | 3/3 | [1, 0, 2] | 3 | intact, 0 edit(s): - | broken, 1 edit(s): replace:guitar case sticker |
| priya | 3/3 | [1, 0, 3] | 3 | broken, 1 edit(s): replace:ferry ticket | broken, 1 edit(s): erase:ferry ticket stub |
