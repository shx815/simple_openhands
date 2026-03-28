"""Utilities for code-generation rollout collection before PPO training."""

from __future__ import annotations

import gc
import json
import re
import traceback
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

try:
    from peft import PeftModel
except ImportError:  # pragma: no cover
    PeftModel = None


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


def infer_dtype() -> torch.dtype | None:
    if torch.cuda.is_available():
        return torch.bfloat16
    return None


def extract_asserts(test_code: str) -> list[str]:
    lines = [line.strip() for line in test_code.replace("\r\n", "\n").split("\n")]
    return [line for line in lines if line.startswith("assert ")]


def align_entry_point(generated_solution: str, entry_point: str) -> str:
    normalized = generated_solution.replace("\r\n", "\n").rstrip()
    if not entry_point or f"def {entry_point}(" in normalized:
        return normalized

    function_names = re.findall(r"(?m)^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", normalized)
    unique_names = list(dict.fromkeys(function_names))
    if len(unique_names) != 1:
        return normalized

    source_name = unique_names[0]
    if source_name == entry_point:
        return normalized
    return normalized + f"\n\n{entry_point} = {source_name}\n"


class CodePolicy:
    """Load a base or SFT model and expose generation/logprob helpers."""

    def __init__(
        self,
        base_model_path: str,
        trust_remote_code: bool,
        adapter_path: str | None = None,
        trainable_adapter: bool = False,
        prompt_template: str = "### Problem:\n{prompt}\n\n### Solution:\n",
    ) -> None:
        self.prompt_template = prompt_template
        self.tokenizer = AutoTokenizer.from_pretrained(
            base_model_path,
            trust_remote_code=trust_remote_code,
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        self.model = AutoModelForCausalLM.from_pretrained(
            base_model_path,
            trust_remote_code=trust_remote_code,
            dtype=infer_dtype(),
            device_map="auto" if torch.cuda.is_available() else None,
        )
        if adapter_path is not None:
            if PeftModel is None:
                raise ImportError("peft is required to load the SFT adapter.")
            self.model = PeftModel.from_pretrained(
                self.model,
                adapter_path,
                is_trainable=trainable_adapter,
            )
        self.model.eval()

    def unload(self) -> None:
        del self.model
        del self.tokenizer
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def format_prompt(self, prompt: str) -> str:
        return self.prompt_template.format(prompt=prompt)

    def generate(self, prompt: str, max_new_tokens: int = 256) -> dict[str, Any]:
        prompt_text = self.format_prompt(prompt)
        inputs = self.tokenizer(prompt_text, return_tensors="pt")
        if hasattr(self.model, "device"):
            inputs = {key: value.to(self.model.device) for key, value in inputs.items()}

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
                return_dict_in_generate=True,
            )

        full_ids = outputs.sequences[0]
        prompt_len = inputs["input_ids"].shape[1]
        response_ids = full_ids[prompt_len:]
        full_text = self.tokenizer.decode(full_ids, skip_special_tokens=True)
        if full_text.startswith(prompt_text):
            response_text = full_text[len(prompt_text) :].strip()
        else:
            response_text = full_text.strip()

        return {
            "prompt_text": prompt_text,
            "response_text": response_text,
            "response_token_count": int(response_ids.shape[0]),
            "sequence_ids": full_ids.detach().cpu(),
            "prompt_length": prompt_len,
        }

    def response_logprob(self, prompt_text: str, response_text: str) -> float:
        with torch.no_grad():
            logprob, _ = self.response_stats(prompt_text=prompt_text, response_text=response_text)
        return float(logprob.item())

    def response_stats(
        self, prompt_text: str, response_text: str
    ) -> tuple[torch.Tensor, torch.Tensor]:
        full_text = prompt_text + response_text
        tokenized = self.tokenizer(full_text, return_tensors="pt")
        if hasattr(self.model, "device"):
            tokenized = {key: value.to(self.model.device) for key, value in tokenized.items()}

        input_ids = tokenized["input_ids"]
        attention_mask = tokenized["attention_mask"]
        prompt_ids = self.tokenizer(prompt_text, return_tensors="pt")["input_ids"]
        prompt_length = int(prompt_ids.shape[1])

        outputs = self.model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            output_hidden_states=True,
        )
        logits = outputs.logits
        hidden_states = outputs.hidden_states[-1]

        log_probs = torch.log_softmax(logits[:, :-1, :], dim=-1)
        target_ids = input_ids[:, 1:]

        response_start = max(prompt_length - 1, 0)
        if response_start >= target_ids.shape[1]:
            pooled_hidden = hidden_states[:, -1, :]
            return torch.zeros((), device=self.model.device), pooled_hidden.squeeze(0)

        selected = log_probs[:, response_start:, :].gather(
            2, target_ids[:, response_start:].unsqueeze(-1)
        )
        response_hidden_start = min(prompt_length, hidden_states.shape[1] - 1)
        response_hidden = hidden_states[:, response_hidden_start:, :]
        pooled_hidden = response_hidden.mean(dim=1)
        return selected.sum(), pooled_hidden.squeeze(0)


class LocalCodeSandboxEnv:
    """Minimal local execution environment for prompt -> code -> reward."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        self.current_record: dict[str, Any] | None = None

    def reset(self, index: int) -> dict[str, Any]:
        self.current_record = self.records[index]
        return {
            "task_id": self.current_record["task_id"],
            "prompt": self.current_record["prompt"],
            "entry_point": self.current_record["entry_point"],
            "metadata": self.current_record.get("metadata", {}),
        }

    def step(self, generated_solution: str) -> tuple[dict[str, Any], float, bool, dict[str, Any]]:
        if self.current_record is None:
            raise RuntimeError("reset() must be called before step().")

        namespace: dict[str, Any] = {"__builtins__": __builtins__}
        test_cases = extract_asserts(str(self.current_record["test_code"]))
        aligned_solution = align_entry_point(
            generated_solution=generated_solution,
            entry_point=str(self.current_record["entry_point"]),
        )

        try:
            exec(aligned_solution + "\n", namespace, namespace)
        except Exception:
            info = {
                "passed": False,
                "passed_tests": 0,
                "total_tests": len(test_cases),
                "error_type": "generation_execution_error",
                "content": traceback.format_exc(),
            }
            return {"task_id": self.current_record["task_id"]}, 0.0, True, info

        passed_tests = 0
        failure_trace = None
        for test_case in test_cases:
            try:
                exec(test_case + "\n", namespace, namespace)
                passed_tests += 1
            except Exception:
                if failure_trace is None:
                    failure_trace = traceback.format_exc()

        total_tests = len(test_cases)
        reward = 0.0 if total_tests == 0 else round(passed_tests / total_tests, 4)
        passed = passed_tests == total_tests
        info = {
            "passed": passed,
            "passed_tests": passed_tests,
            "total_tests": total_tests,
            "error_type": None if passed else "partial_or_failed_tests",
            "content": "" if passed else (failure_trace or ""),
        }
        return {"task_id": self.current_record["task_id"]}, reward, True, info


def compute_batch_advantages(rewards: list[float]) -> list[float]:
    if not rewards:
        return []
    baseline = sum(rewards) / len(rewards)
    return [round(reward - baseline, 6) for reward in rewards]
