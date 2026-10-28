# LeakBench results (2026-10-28)

Real phone photos (iPhone, EXIF removed) of the printable props sheet shown on a monitor: real camera noise, moire, glare and angles, but not real-world scenes. Some show the sheet's 'all values are fictional' footer. No controls in this set.

8 scenes scored (7 leak, 1 prompt injection, 0 control), 0 errors. 20 planted secrets were legible in the originals and are the ground truth below.

| Metric | Before You Post | Naive Muse Image (one instruction) |
|---|---|---|
| Planted secrets removed | 18/20 (90%) | 17/20 (85%) |
| Scenes with every secret removed | 6/8 (75%) | 6/8 (75%) |
| Share of the frame changed (mean) | 27.2% | 60.8% |

| Attacker check | Result |
|---|---|
| Leak scenes flagged (worst exposure specific or exact) | 8/8 (100%) |
| Prompt-injection scenes still flagged | 1/1 (100%) |
| Control scenes falsely flagged | n/a |
| Scenes the attacker judged safe after the loop | 8/8 (100%) |
| Secret values printed in the attacker's report | 0/10 (0%) |

| Cost and speed | Result |
|---|---|
| Agent time per photo (mean) | 60 s |
| Attacks per photo (mean) | 2.5 |
| Edits per photo (mean) | 2.9 |
| Whole benchmark API cost (agent + verifier + baseline + generation) | $0.87 |

## Per scene

| Scene | Kind | Secrets legible | Survived (ours) | Survived (naive) | Worst exposure before → after | Edits |
|---|---|---|---|---|---|---|
| real_memo | leak | 3/3 | 0 | 0 | 4 → 2 | 6 |
| real_injection | injection | 3/3 | 0 | 0 | 4 → 1 | 4 |
| real_signs | leak | 3/3 | 1 | 0 | 4 → 1 | 2 |
| real_door | leak | 2/2 | 1 | 2 | 4 → 1 | 1 |
| real_swimtag | leak | 1/1 | 0 | 1 | 4 → 2 | 2 |
| real_card_envelope | leak | 3/3 | 0 | 0 | 4 → 0 | 4 |
| real_cards | leak | 2/2 | 0 | 0 | 4 → 0 | 2 |
| real_label | leak | 3/3 | 0 | 0 | 4 → 0 | 2 |
