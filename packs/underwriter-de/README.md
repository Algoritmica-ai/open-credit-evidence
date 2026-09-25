# underwriter-de

The twenty referred personal-loan cases of [`underwriter-sample`](../underwriter-sample/),
for a German public lender: amounts in euros and the German rule pack
([`regulations/DE`](../../regulations/DE/)) as the jurisdiction overlay. Same generator,
seed and scorecard, so the same applicants, the same decisions and the same marking key;
only the currency in the case file and the regulatory context differ. How the cases are
built and what each file is: see the sample pack's README.

Rebuild with:

```bash
.venv/bin/python -m evidence.packs.credit_underwriting --n 700 --keep 20 --seed 7 \
  --market de --pack-id underwriter-de --out packs/underwriter-de
```
