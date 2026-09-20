# nerodyne live record

This repository exists to be checked, not read.

It holds the public record of every basket the Nova model has published. They are here because a
timestamp you control yourself is worth nothing. The commit history is the evidence: each basket
appears in it before the market opened on the day it was traded.

## What is in here

| File | What it is |
|---|---|
| PROOF.txt | Each basket, when it was published, and its fingerprint |
| live_record.json | The full record, including the fills that came back from the broker |
| live_record_public.json | The same thing shaped for the website, refreshed on a schedule |
| update_record.py | Asks the broker what the open position is worth. Never edits history |

## How to verify a basket

Each basket has a SHA-256 fingerprint of its signal date, a vertical bar, and its tickers in
alphabetical order separated by commas. Recompute it:

    python -c "import hashlib; print(hashlib.sha256(b'2026-09-01|ADI,CRM,DELL,EXPE,GEN,MPC,MU,PAGP,PWR,VRT').hexdigest())"

If that matches PROOF.txt, and the commit that introduced it predates the trading session, then
the basket was fixed before anyone knew what it would do.

## What this record does not prove

Check the mode field. While it reads "paper" the capital is simulated, which removes the only
genuinely hard part, which is holding a position through a fall with your own money at stake. The
baskets and the prices are real either way. The money may not be.

## Setup

Three repository secrets: ALPACA_KEY, ALPACA_SECRET and ALPACA_BASE. No credential is ever written
into a committed file, and the updater refuses to write its output if it finds one there.
