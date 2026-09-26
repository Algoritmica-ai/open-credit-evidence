# Anchoring: proof outside our control

A test is sealed by `checksums.sha256`, a SHA-256 for every file in it. The SHA-256 of that
file is the test's **seal**. A seal shows whether a file changed, but whoever holds the files
could change one and seal them again. Anchoring removes that possibility: the seal is written
into the Bitcoin blockchain through [OpenTimestamps](https://opentimestamps.org), where
nobody can change it afterwards, including us.

The code is `src/evidence/anchor.py`. It is standalone, can be switched off, and does nothing
when the `opentimestamps` package is not installed.

## What it costs, and what leaves the machine

- **No money.** OpenTimestamps' public calendar servers gather thousands of fingerprints
  from everyone into one Bitcoin transaction and pay its fee. A bank that runs its own
  calendar (open source) pays that one fee per batch: cents to a few dollars, however many
  fingerprints are in it.
- **Only a 32-byte fingerprint.** No file, no memo, no case data. It is mixed with a random
  value before it is sent, so a calendar can't even tell which fingerprint it received.

## How it works

1. **Sent.** When a test finishes, the seal goes to four public calendars. Each answers at
   once with a *pending* proof, kept in `anchors/001.ots`.
2. **Batched.** A calendar combines every fingerprint it received into one hash (a Merkle
   tree) and puts that hash into a Bitcoin transaction.
3. **Confirmed.** Once the transaction is in a block, usually within a few hours, the
   complete proof is fetched: the hash steps from the seal up to that block. The UI server
   does this every 30 minutes; `evidence anchor <run> --upgrade` does it by hand.
4. **Checked.** `evidence verify` recomputes the steps and compares the result with the
   block, as two public block explorers report it. After that the proof depends on nothing
   but Bitcoin.

It proves the files existed, unchanged, no later than the block's time. It does not prove
who made them. A signature in a public log (Sigstore Rekor) would add that later, in the
same records.

## Milestones, and what a later change means

A test keeps changing after it is sealed: reviews, rulings and the feedback pack are added,
and each change seals it again. So we anchor milestones:

| Milestone | When |
|---|---|
| `test` | The test finishes (the memos, the check results, the decision) |
| `feedback-pack` | Each time the feedback pack is built |
| `manual` | `evidence anchor <run>` or **Anchor now** in the UI |

Each anchor keeps a copy of the file list it anchored (`anchors/001-checksums.sha256`), so
`evidence verify` can say which files are unchanged since and which were added later. Review
files added after a test are expected. A changed memo (`transcripts/`), check result
(`results.jsonl`) or manifest fails verification, even if the test was sealed again after
the change. Each anchor record names the one before it, so the records form a chain.

`anchors/` sits inside the test folder but outside its seal, because a seal can't contain its
own proof. Copying a test folder copies its proofs.

## Check a proof without our software

Anyone can check an anchor with the official OpenTimestamps client:

```bash
pip install opentimestamps-client
```

```bash
ots verify -f runs/<test>/anchors/001-checksums.sha256 runs/<test>/anchors/001.ots
```

`ots` needs a Bitcoin node to check against, or use `ots info` to read the proof and compare
the block with any block explorer. `evidence verify` does the same comparison against two
public explorers.

## Settings

| Setting | Default | What it does |
|---|---|---|
| `EVIDENCE_ANCHOR` | `on` | `off` switches anchoring off entirely |
| `EVIDENCE_ANCHOR_CALENDARS` | the four public OpenTimestamps aggregators | Comma-separated calendar URLs, for example a bank's own |
| `EVIDENCE_ANCHOR_EXPLORERS` | blockstream.info and mempool.space | Comma-separated block explorer APIs used to check proofs, for example a bank's own node's |
| `EVIDENCE_ANCHOR_UPGRADE_S` | 1800 | How often the UI server collects confirmed proofs, in seconds |

A calendar that can't be reached never holds up a test. The anchor is recorded as not sent,
and tried again automatically.
