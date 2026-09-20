# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Smallest possible LoRA fine-tune: 8 made-up examples, 10 steps.

Its only job is to prove the loop works on this node before real data exists:
the model loads, LoRA attaches to a small fraction of the weights, the loss
falls, and an adapter is written to disk. Run inside an srun session:

    ~/venvs/ft/bin/python ~/open-credit-evidence/scripts/finetune/smoke_lora.py

Every block below is one stage of the recipe; the comments say why it is there.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = Path("/data/team08/models/nemotron-nano-9b-v2")
OUT = Path("/data/team08/runs/smoke")
STEPS = 10
BATCH = 2
LR = 2e-4
SEED = 7

# ---------------------------------------------------------------------------
# 1. Examples. The real ones will come from Ultra. These eight exist only so
#    the loop has something to chew on. Same shape as the real task: a system
#    rubric, a user turn with the briefing, and the exact JSON we want back.
# ---------------------------------------------------------------------------
RUBRIC = (
    "Grade the underwriter briefing for readability only. Reply with JSON: "
    '{"intelligible": 0-2, "actionable": 0-2, "reason": "..."}'
)
EXAMPLES = [
    ("The applicant's debt service is 47% of income, above the 40% policy limit. "
     "Reducing the instalment to £189 would bring it within policy.",
     {"intelligible": 2, "actionable": 2, "reason": "States the breach and the fix."}),
    ("Affordability concerns exist. Various factors apply.",
     {"intelligible": 0, "actionable": 0, "reason": "Says nothing specific."}),
    ("Bureau score 652, no missed payments. Debt service 47% exceeds 40%.",
     {"intelligible": 2, "actionable": 1, "reason": "Clear facts; no route to another outcome."}),
    ("The ratio is high. Consider options.",
     {"intelligible": 1, "actionable": 0, "reason": "Vague on both counts."}),
    ("Income £15,922 verified. Commitments £316 plus instalment £314 give 47%. "
     "A longer term or lower amount would bring the ratio under 40%.",
     {"intelligible": 2, "actionable": 2, "reason": "Numbers and the change needed."}),
    ("Applicant is 55-64, self-employed, three dependants. Referred for review.",
     {"intelligible": 1, "actionable": 0, "reason": "Lists fields; no reason for review."}),
    ("Debt service 47% against a 40% limit. No missed payments in 24 months.",
     {"intelligible": 2, "actionable": 1, "reason": "Breach stated; change not stated."}),
    ("Please review.",
     {"intelligible": 0, "actionable": 0, "reason": "Empty."}),
]

# ---------------------------------------------------------------------------
# 2. Tokeniser and model. bf16 halves memory against fp32 with no practical
#    loss for training a LoRA. trust_remote_code: the folder ships its own
#    modeling_nemotron_h.py and transformers must be told to use it.
# ---------------------------------------------------------------------------
torch.manual_seed(SEED)
t0 = time.perf_counter()
tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    MODEL, dtype=torch.bfloat16, device_map="cuda", trust_remote_code=True
)
print(f"loaded {MODEL.name} in {time.perf_counter() - t0:.0f}s; "
      f"GPU memory {torch.cuda.memory_allocated() / 2**30:.1f} GiB")

# ---------------------------------------------------------------------------
# 3. LoRA. Freeze everything, then add trainable low-rank pairs to every
#    linear layer. "all-linear" rather than the usual q/k/v/o list because
#    this model is mostly Mamba layers; only 4 of 56 have attention.
#    The printed line must show a small percentage. 100% means it did not attach.
# ---------------------------------------------------------------------------
lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, target_modules="all-linear",
                  task_type="CAUSAL_LM")
model = get_peft_model(model, lora)
model.print_trainable_parameters()

# ---------------------------------------------------------------------------
# 4. Turn each example into token ids, and build the "labels" the loss is
#    measured against. Key idea: we mask the prompt with -100 so the loss only
#    counts the answer tokens. We are teaching the model what to *say*, not
#    to predict the rubric and briefing it was given.
# ---------------------------------------------------------------------------
def encode(briefing: str, answer: dict) -> dict[str, torch.Tensor]:
    msgs = [{"role": "system", "content": RUBRIC}, {"role": "user", "content": briefing}]
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    full = prompt + json.dumps(answer) + tok.eos_token
    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    f_ids = tok(full, add_special_tokens=False)["input_ids"]
    labels = [-100] * len(p_ids) + f_ids[len(p_ids):]
    return {"input_ids": torch.tensor(f_ids), "labels": torch.tensor(labels)}

encoded = [encode(b, a) for b, a in EXAMPLES]
print(f"{len(encoded)} examples, {sum(len(e['input_ids']) for e in encoded)} tokens, "
      f"{sum((e['labels'] != -100).sum().item() for e in encoded)} of them answer tokens")

def batch(items: list[dict]) -> dict[str, torch.Tensor]:
    """Pad to the longest in the batch. Pads get label -100 so they are ignored too."""
    n = max(len(i["input_ids"]) for i in items)
    ids = torch.full((len(items), n), tok.pad_token_id or tok.eos_token_id)
    lab = torch.full((len(items), n), -100)
    att = torch.zeros((len(items), n), dtype=torch.long)
    for r, i in enumerate(items):
        k = len(i["input_ids"])
        ids[r, :k], lab[r, :k], att[r, :k] = i["input_ids"], i["labels"], 1
    return {"input_ids": ids.cuda(), "labels": lab.cuda(), "attention_mask": att.cuda()}

# ---------------------------------------------------------------------------
# 5. The training loop, undisguised. forward -> loss -> backward -> step.
#    Only the LoRA weights receive gradients; the optimiser only knows about
#    those. On 8 examples the loss should fall clearly within 10 steps —
#    that is memorisation, which is exactly what we want to see here.
# ---------------------------------------------------------------------------
opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=LR)
model.train()
t0 = time.perf_counter()
for step in range(STEPS):
    items = [encoded[(step * BATCH + j) % len(encoded)] for j in range(BATCH)]
    out = model(**batch(items))
    out.loss.backward()
    opt.step()
    opt.zero_grad()
    print(f"step {step + 1:2d}/{STEPS}  loss {out.loss.item():.3f}")
print(f"trained in {time.perf_counter() - t0:.0f}s; "
      f"peak GPU memory {torch.cuda.max_memory_allocated() / 2**30:.1f} GiB")

# ---------------------------------------------------------------------------
# 6. Save only the adapter — the sticky notes, not the book. Then reload the
#    tokeniser next to it and generate on one example to prove it produces
#    something JSON-shaped. Expect imperfect output: 10 steps is not training.
# ---------------------------------------------------------------------------
OUT.mkdir(parents=True, exist_ok=True)
model.save_pretrained(OUT / "adapter")
tok.save_pretrained(OUT / "adapter")
size = sum(f.stat().st_size for f in (OUT / "adapter").rglob("*") if f.is_file()) / 2**20
print(f"adapter saved to {OUT / 'adapter'} ({size:.0f} MiB)")

model.eval()
msgs = [{"role": "system", "content": RUBRIC},
        {"role": "user", "content": "Debt service 47% against a 40% limit. Reduce the amount."}]
ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt").to("cuda")
with torch.no_grad():
    gen = model.generate(ids, max_new_tokens=60, do_sample=False)
print("sample output:", tok.decode(gen[0][ids.shape[1]:], skip_special_tokens=True).strip())
