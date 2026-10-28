# Account LeakBench (2026-10-28, standard mode)

5 staged accounts of 3 photos, 0 errors. In each, one photo shows a first name, one a kind of job or routine, one a town: harmless alone, identifying together. A combination is broken when at least one of its legible pieces is gone from the final photos, as read by a separate transcription pass.

| | One photo at a time | As one account |
|---|---|---|
| Combinations broken | 2/5 | 5/5 |
| Edits made | 2 | 7 |
| Photos changed | 2/15 | 6/15 |
| Share of each photo changed (mean) | 0.3% | 1.8% |
| Time per account (mean, the three single runs in parallel) | 34 s | 80 s |

Whole run cost (estimate, including the verifier): $0.74

## Per account

| Account | Pieces legible | Worst exposure, each photo alone | Worst exposure together | One at a time | As one account |
|---|---|---|---|---|---|
| mina | 2/2 | [1, 1, 2] | 3 | intact, 0 edit(s): - | broken, 3 edit(s): replace:stack of lab papers, pixelate:classroom lab microscope, replace:folded local newspaper |
| daniel | 3/3 | [1, 1, 2] | 3 | intact, 0 edit(s): - | broken, 1 edit(s): replace:town welcome sign |
| yuna | 3/3 | [1, 1, 2] | 3 | intact, 0 edit(s): - | broken, 1 edit(s): replace:chocolate message plaque |
| leo | 3/3 | [1, 1, 3] | 3 | broken, 1 edit(s): replace:transit card | broken, 1 edit(s): replace:guitar case sticker |
| priya | 3/3 | [1, 1, 3] | 3 | broken, 1 edit(s): replace:ferry ticket stub | broken, 1 edit(s): replace:ferry ticket |
