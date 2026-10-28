# Account LeakBench (2026-10-28, private mode (Muse Spark Open, edits on the server))

5 staged accounts of 3 photos, 0 errors. In each, one photo shows a first name, one a kind of job or routine, one a town: harmless alone, identifying together. A combination is broken when at least one of its legible pieces is gone from the final photos, as read by a separate transcription pass.

| | One photo at a time | As one account |
|---|---|---|
| Combinations broken | 4/5 | 5/5 |
| Edits made | 4 | 9 |
| Photos changed | 4/15 | 9/15 |
| Share of each photo changed (mean) | 3.1% | 4.8% |
| Time per account (mean, the three single runs in parallel) | 17 s | 32 s |

Whole run cost (estimate, including the verifier): $0.56

## Per account

| Account | Pieces legible | Worst exposure, each photo alone | Worst exposure together | One at a time | As one account |
|---|---|---|---|---|---|
| mina | 2/2 | [1, 2, 3] | 3 | broken, 1 edit(s): pixelate:folded newspaper | broken, 2 edit(s): pixelate:folded newspaper, pixelate:stack of lab reports |
| daniel | 3/3 | [1, 2, 3] | 3 | broken, 1 edit(s): pixelate:wooden welcome sign | broken, 2 edit(s): pixelate:welcome sign, pixelate:birthday cake |
| yuna | 3/3 | [1, 2, 0] | 3 | intact, 0 edit(s): - | broken, 2 edit(s): pixelate:chocolate plaque, pixelate:open notebook page |
| leo | 3/3 | [1, 1, 3] | 3 | broken, 1 edit(s): pixelate:plastic transit card | broken, 1 edit(s): pixelate:transit card |
| priya | 3/3 | [1, 2, 3] | 3 | broken, 1 edit(s): pixelate:ferry ticket | broken, 2 edit(s): pixelate:personalized coffee mug, pixelate:ferry ticket |
