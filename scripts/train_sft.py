#!/usr/bin/env python3
"""Minimal SFT training entrypoint for code-generation data."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
    set_seed,
)

try:
    from peft import LoraConfig, get_peft_model
except ImportError:  # pragma: no cover
    LoraConfig = None
    get_peft_model = None


REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a code SFT model with JSON config.")
    parser.add_argument(
        "--config",
        default="configs/sft_qwen25_coder_15b_lora.json",
        help="Path to JSON config file.",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return records


@dataclass
class Example:
    prompt: str
    response: str


class SFTJsonlDataset(Dataset):
    """Tokenize prompt-response examples and mask prompt tokens from the loss."""

    def __init__(
        self,
        records: list[dict[str, Any]],
        tokenizer: Any,
        max_length: int,
        prompt_template: str,
    ) -> None:
        self.examples = [
            Example(prompt=str(record["prompt"]), response=str(record["response"]))
            for record in records
        ]
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.prompt_template = prompt_template

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        example = self.examples[index]
        prompt_text = self.prompt_template.format(prompt=example.prompt)
        full_text = prompt_text + example.response + self.tokenizer.eos_token

        prompt_tokens = self.tokenizer(
            prompt_text,
            add_special_tokens=False,
            truncation=True,
            max_length=self.max_length,
        )
        full_tokens = self.tokenizer(
            full_text,
            add_special_tokens=False,
            truncation=True,
            max_length=self.max_length,
        )

        input_ids = full_tokens["input_ids"]
        attention_mask = full_tokens["attention_mask"]
        labels = input_ids.copy()

        prompt_token_count = min(len(prompt_tokens["input_ids"]), len(labels))
        for idx in range(prompt_token_count):
            labels[idx] = -100

        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(attention_mask, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
        }


class DataCollatorForCausalSFT:
    def __init__(self, tokenizer: Any) -> None:
        self.tokenizer = tokenizer

    def __call__(self, features: list[dict[str, torch.Tensor]]) -> dict[str, torch.Tensor]:
        input_ids = [feature["input_ids"] for feature in features]
        attention_mask = [feature["attention_mask"] for feature in features]
        labels = [feature["labels"] for feature in features]

        batch_input_ids = torch.nn.utils.rnn.pad_sequence(
            input_ids,
            batch_first=True,
            padding_value=self.tokenizer.pad_token_id,
        )
        batch_attention_mask = torch.nn.utils.rnn.pad_sequence(
            attention_mask,
            batch_first=True,
            padding_value=0,
        )
        batch_labels = torch.nn.utils.rnn.pad_sequence(
            labels,
            batch_first=True,
            padding_value=-100,
        )

        return {
            "input_ids": batch_input_ids,
            "attention_mask": batch_attention_mask,
            "labels": batch_labels,
        }


def build_model_and_tokenizer(config: dict[str, Any]) -> tuple[Any, Any]:
    tokenizer = AutoTokenizer.from_pretrained(
        config["model_name_or_path"],
        trust_remote_code=config.get("trust_remote_code", False),
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    torch_dtype = None
    if config.get("bf16", False) and torch.cuda.is_available():
        torch_dtype = torch.bfloat16

    model = AutoModelForCausalLM.from_pretrained(
        config["model_name_or_path"],
        trust_remote_code=config.get("trust_remote_code", False),
        torch_dtype=torch_dtype,
    )

    if config.get("gradient_checkpointing", False):
        model.gradient_checkpointing_enable()
        model.config.use_cache = False

    if config.get("use_lora", False):
        if LoraConfig is None or get_peft_model is None:
            raise ImportError(
                "peft is required when use_lora=true. Install it before training."
            )

        lora_config = LoraConfig(
            r=config["lora_r"],
            lora_alpha=config["lora_alpha"],
            lora_dropout=config["lora_dropout"],
            target_modules=config["lora_target_modules"],
            bias="none",
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()

    return model, tokenizer


def build_training_arguments(config: dict[str, Any]) -> TrainingArguments:
    output_dir = str((REPO_ROOT / config["output_dir"]).resolve())
    return TrainingArguments(
        output_dir=output_dir,
        overwrite_output_dir=True,
        num_train_epochs=config["num_train_epochs"],
        per_device_train_batch_size=config["per_device_train_batch_size"],
        per_device_eval_batch_size=config["per_device_eval_batch_size"],
        gradient_accumulation_steps=config["gradient_accumulation_steps"],
        learning_rate=config["learning_rate"],
        weight_decay=config["weight_decay"],
        warmup_ratio=config["warmup_ratio"],
        logging_steps=config["logging_steps"],
        evaluation_strategy="steps",
        eval_steps=config["eval_steps"],
        save_steps=config["save_steps"],
        save_total_limit=config["save_total_limit"],
        bf16=config.get("bf16", False),
        fp16=config.get("fp16", False),
        gradient_checkpointing=config.get("gradient_checkpointing", False),
        lr_scheduler_type=config.get("lr_scheduler_type", "cosine"),
        report_to=config.get("report_to", []),
        remove_unused_columns=False,
        dataloader_num_workers=config.get("dataloader_num_workers", 0),
        logging_dir=str((REPO_ROOT / config["output_dir"] / "logs").resolve()),
        seed=config["seed"],
    )


def main() -> int:
    args = parse_args()
    config_path = (REPO_ROOT / args.config).resolve()
    config = load_config(config_path)

    random.seed(config["seed"])
    np.random.seed(config["seed"])
    set_seed(config["seed"])

    train_records = load_jsonl((REPO_ROOT / config["train_file"]).resolve())
    valid_records = load_jsonl((REPO_ROOT / config["valid_file"]).resolve())

    model, tokenizer = build_model_and_tokenizer(config)
    prompt_template = config.get("prompt_template", "{prompt}\n")

    train_dataset = SFTJsonlDataset(
        train_records,
        tokenizer=tokenizer,
        max_length=config["max_length"],
        prompt_template=prompt_template,
    )
    valid_dataset = SFTJsonlDataset(
        valid_records,
        tokenizer=tokenizer,
        max_length=config["max_length"],
        prompt_template=prompt_template,
    )

    training_args = build_training_arguments(config)
    collator = DataCollatorForCausalSFT(tokenizer)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=valid_dataset,
        data_collator=collator,
        tokenizer=tokenizer,
    )

    trainer.train()
    trainer.save_model()
    tokenizer.save_pretrained(training_args.output_dir)

    metrics = trainer.evaluate()
    metrics_path = Path(training_args.output_dir) / "eval_metrics.json"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
