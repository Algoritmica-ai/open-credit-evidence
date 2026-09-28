# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The NeMo AutoModel configuration for a LoRA fine-tune of Nemotron 3.5 Lightning.

Written from a training folder made by ``evidence distill`` (its ``sft/train.jsonl`` and
``sft/val.jsonl``). Based on NVIDIA's recipe for the same architecture
(``examples/llm_finetune/nemotron/customizer_nemotron_nano_peft.yaml`` in the
``nvcr.io/nvidia/nemo-automodel`` container), with these choices:

- **The chat format the model is served with.** The engine calls Lightning with thinking
  off; the model's chat template defaults to thinking on. The template here is the model's
  own with that default turned off, so every example reads exactly as the NIM renders the
  prompt (ending ``<think></think>``), then the memo. Checked before training: the rendered
  prompt is a prefix of the rendered example.
- **Loss on the memo only** (the chat dataset masks the prompt).
- **LoRA rank 16** on every linear layer except the Mamba ``out_proj`` (custom kernels),
  as in NVIDIA's recipe.

Run inside the container (see ``train_lightning.sh``)::

    python lightning_lora.py --model /repo/snapshots/hf-b3caaab --data /data/<name> \\
        --out /out/<name> --gpus 2 > /out/<name>/config.yaml
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

THINKING_DEFAULT = ("{%- set enable_thinking = enable_thinking if enable_thinking is defined "
                    "else True %}")


def chat_template(model: Path) -> str:
    tpl = (model / "chat_template.jinja").read_text(encoding="utf-8")
    if THINKING_DEFAULT not in tpl:
        raise SystemExit("the model's chat template has changed: check the thinking default")
    return tpl.replace(THINKING_DEFAULT, THINKING_DEFAULT.replace("else True", "else False"))


def config(model: Path, data: Path, out: Path, *, gpus: int, epochs: int, lr: float,
           rank: int, global_batch: int, seq_length: int) -> dict:
    n_train = sum(1 for line in (data / "sft/train.jsonl").open() if line.strip())
    steps = max(1, math.ceil(n_train * epochs / global_batch))
    every = max(1, min(50, steps // 4))
    tpl = chat_template(model)

    def dataset(split: str) -> dict:
        return {"_target_": "nemo_automodel.components.datasets.llm.chat_dataset.ChatDataset",
                "path_or_dataset_id": str(data / f"sft/{split}.jsonl"), "split": "train",
                "seq_length": seq_length, "chat_template": tpl, "padding": "do_not_pad",
                "truncation": "do_not_truncate"}

    loader = {"_target_": "torchdata.stateful_dataloader.StatefulDataLoader",
              "collate_fn": "nemo_automodel.components.datasets.utils.default_collater"}
    return {
        "recipe": "TrainFinetuneRecipeForNextTokenPrediction",
        "dist_env": {"backend": "nccl", "timeout_minutes": 30},
        "rng": {"_target_": "nemo_automodel.components.training.rng.StatefulRNG",
                "seed": 1111, "ranked": True},
        "model": {"_target_": "nemo_automodel.NeMoAutoModelForCausalLM.from_pretrained",
                  "pretrained_model_name_or_path": str(model), "torch_dtype": "bfloat16",
                  "trust_remote_code": True, "attn_implementation": "sdpa",
                  "backend": {"_target_": "nemo_automodel.components.models.common.utils."
                                         "BackendConfig", "experts": "gmm",
                              "dispatcher": "torch"}},
        "distributed": {"_target_": "nemo_automodel.components.distributed.fsdp2.FSDP2Manager",
                        "dp_size": None, "tp_size": 1, "pp_size": 1, "cp_size": 1,
                        "ep_size": gpus, "sequence_parallel": False},
        "parallelizer": {"_target_": "nemo_automodel.components.moe.parallelizer."
                                     "parallelize_model", "activation_checkpointing": True},
        "step_scheduler": {"global_batch_size": global_batch, "local_batch_size": 1,
                           "max_steps": steps, "num_epochs": epochs,
                           "val_every_steps": every, "ckpt_every_steps": every},
        "optimizer": {"_target_": "torch.optim.AdamW", "lr": lr, "weight_decay": 0.01,
                      "betas": [0.9, 0.999], "eps": 1.0e-8},
        "lr_scheduler": {"lr_decay_style": "cosine", "lr_warmup_steps": max(1, steps // 20),
                         "min_lr": lr / 10},
        "peft": {"_target_": "nemo_automodel.components._peft.lora.PeftConfig",
                 "dim": rank, "alpha": 2 * rank, "dropout": 0.0, "use_triton": True,
                 "exclude_modules": ["*.out_proj"]},
        "loss_fn": {"_target_": "nemo_automodel.components.loss.masked_ce.MaskedCrossEntropy"},
        "checkpoint": {"enabled": True, "model_save_format": "safetensors",
                       "checkpoint_dir": str(out / "checkpoints"), "save_consolidated": True},
        "dataset": dataset("train"), "validation_dataset": dataset("val"),
        "dataloader": {**loader, "shuffle": True}, "validation_dataloader": loader,
        "_meta": {"train_examples": n_train, "steps": steps, "gpus": gpus},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--gpus", type=int, default=2)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--global-batch", type=int, default=16)
    ap.add_argument("--seq-length", type=int, default=3072)
    ap.add_argument("--max-steps", type=int, help="stop early (a smoke test)")
    a = ap.parse_args()
    cfg = config(a.model, a.data, a.out, gpus=a.gpus, epochs=a.epochs, lr=a.lr, rank=a.rank,
                 global_batch=a.global_batch, seq_length=a.seq_length)
    if a.max_steps:
        cfg["step_scheduler"].update(max_steps=a.max_steps, val_every_steps=a.max_steps,
                                     ckpt_every_steps=a.max_steps)
    meta = cfg.pop("_meta")
    print(f"# {meta['train_examples']} examples, {cfg['step_scheduler']['max_steps']} steps, "
          f"{meta['gpus']} GPU(s)", file=sys.stderr)
    import yaml

    yaml.safe_dump(json.loads(json.dumps(cfg)), sys.stdout, sort_keys=False, width=1000)


if __name__ == "__main__":
    main()
