"""Utilities for code-generation rollout collection before PPO training."""

from __future__ import annotations

import ast
import gc
import inspect
import json
import re
import traceback
from collections import Counter
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


def uses_humaneval_check(test_code: str) -> bool:
    normalized = test_code.replace("\r\n", "\n")
    return "def check(candidate):" in normalized and "check(" in normalized


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


def clean_generated_solution(generated_solution: str) -> str:
    """Extract executable Python from model output."""
    normalized = generated_solution.replace("\r\n", "\n").strip()

    fenced_blocks = re.findall(
        r"```(?:python|py)?\s*(.*?)```",
        normalized,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fenced_blocks:
        normalized = next(
            (
                block.strip()
                for block in fenced_blocks
                if re.search(r"(?m)^(from|import|def|class|@)\s+", block.strip())
            ),
            fenced_blocks[0].strip(),
        )

    for marker in ("### Solution:", "Solution:"):
        if marker in normalized:
            normalized = normalized.split(marker, maxsplit=1)[-1].strip()

    lines = normalized.splitlines()
    start_index = None
    for index, line in enumerate(lines):
        if re.match(r"^\s*(from|import|def|class|@)\s+", line):
            start_index = index
            break
    if start_index is not None:
        normalized = "\n".join(lines[start_index:]).strip()

    lines = normalized.splitlines()
    for end_index in range(len(lines), 0, -1):
        candidate = "\n".join(lines[:end_index]).strip()
        if not candidate:
            continue
        try:
            compile(candidate, "<generated_solution>", "exec")
            return candidate
        except SyntaxError:
            continue

    return normalized


def _ast_node_counts(code: str) -> Counter[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return Counter()
    ignored = {"Load", "Store", "Del", "Module"}
    return Counter(
        type(node).__name__
        for node in ast.walk(tree)
        if type(node).__name__ not in ignored
    )


def compute_ast_similarity(generated_solution: str, canonical_solution: str) -> float:
    generated_counts = _ast_node_counts(generated_solution)
    canonical_counts = _ast_node_counts(canonical_solution)
    if not generated_counts or not canonical_counts:
        return 0.0

    overlap = sum(
        min(generated_counts[node_type], canonical_counts[node_type])
        for node_type in generated_counts.keys() | canonical_counts.keys()
    )
    normalizer = max(sum(generated_counts.values()), sum(canonical_counts.values()))
    if normalizer == 0:
        return 0.0
    return round(overlap / normalizer, 4)


def _canonical_arg_count(canonical_solution: str, entry_point: str) -> int | None:
    try:
        tree = ast.parse(canonical_solution)
    except SyntaxError:
        return None

    function_defs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    target = next((node for node in function_defs if node.name == entry_point), None)
    if target is None and function_defs:
        target = function_defs[0]
    if target is None:
        return None

    args = target.args
    count = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
    if args.vararg is not None:
        count += 1
    if args.kwarg is not None:
        count += 1
    return count


def compute_signature_reward(
    namespace: dict[str, Any],
    canonical_solution: str,
    entry_point: str,
) -> float:
    candidate = namespace.get(entry_point)
    if not callable(candidate):
        return 0.0

    canonical_count = _canonical_arg_count(canonical_solution, entry_point)
    if canonical_count is None:
        return 0.0

    try:
        generated_signature = inspect.signature(candidate)
    except (TypeError, ValueError):
        return 0.0
    generated_count = len(generated_signature.parameters)
    return 1.0 if generated_count == canonical_count else 0.0


def compute_shaped_reward(
    passed_tests: int,
    total_tests: int,
    execution_ok: bool,
) -> float:
    """Dense reward for PPO.

    Reward layout:
    - 0.1 for generating executable code
    - 0.8 * test pass ratio
    - 0.1 extra bonus for full pass
    """
    if not execution_ok or total_tests <= 0:
        return 0.0

    pass_ratio = passed_tests / total_tests
    full_pass_bonus = 0.1 if passed_tests == total_tests else 0.0
    reward = 0.1 + 0.8 * pass_ratio + full_pass_bonus
    return round(min(reward, 1.0), 4)


def compute_reward(
    *,
    record: dict[str, Any],
    namespace: dict[str, Any],
    cleaned_solution: str,
    aligned_solution: str,
    passed_tests: int,
    total_tests: int,
    execution_ok: bool,
    reward_mode: str = "v2",
) -> tuple[float, dict[str, float]]:
    if not execution_ok or total_tests <= 0:
        return 0.0, {
            "executable": 0.0,
            "entry_point": 0.0,
            "ast": 0.0,
            "signature": 0.0,
            "test_pass_ratio": 0.0,
            "full_pass": 0.0,
        }

    pass_ratio = passed_tests / total_tests
    full_pass = 1.0 if passed_tests == total_tests else 0.0

    if reward_mode == "v2":
        reward = compute_shaped_reward(
            passed_tests=passed_tests,
            total_tests=total_tests,
            execution_ok=execution_ok,
        )
        return reward, {
            "executable": 1.0,
            "entry_point": 1.0 if str(record["entry_point"]) in namespace else 0.0,
            "ast": 0.0,
            "signature": 0.0,
            "test_pass_ratio": round(pass_ratio, 4),
            "full_pass": full_pass,
        }

    if reward_mode not in {"v3", "v3b"}:
        raise ValueError(f"Unsupported reward_mode: {reward_mode}")

    entry_point = str(record["entry_point"])
    entry_reward = 1.0 if callable(namespace.get(entry_point)) else 0.0
    ast_reward = compute_ast_similarity(
        generated_solution=aligned_solution,
        canonical_solution=str(record.get("canonical_solution", "")),
    )
    signature_reward = compute_signature_reward(
        namespace=namespace,
        canonical_solution=str(record.get("canonical_solution", "")),
        entry_point=entry_point,
    )
    if reward_mode == "v3":
        reward = (
            0.10
            + 0.10 * entry_reward
            + 0.15 * ast_reward
            + 0.10 * signature_reward
            + 0.45 * pass_ratio
            + 0.10 * full_pass
        )
    else:
        reward = (
            0.05
            + 0.05 * entry_reward
            + 0.05 * ast_reward
            + 0.05 * signature_reward
            + 0.70 * pass_ratio
            + 0.10 * full_pass
        )
    components = {
        "executable": 1.0,
        "entry_point": round(entry_reward, 4),
        "ast": round(ast_reward, 4),
        "signature": round(signature_reward, 4),
        "test_pass_ratio": round(pass_ratio, 4),
        "full_pass": full_pass,
    }
    return round(min(reward, 1.0), 4), components


def execute_test_code(
    namespace: dict[str, Any],
    record: dict[str, Any],
) -> tuple[int, int, str | None]:
    test_code = str(record["test_code"])

    if uses_humaneval_check(test_code):
        try:
            exec(test_code + "\n", namespace, namespace)
            return 1, 1, None
        except Exception:
            return 0, 1, traceback.format_exc()

    test_cases = extract_asserts(test_code)
    passed_tests = 0
    failure_trace = None
    for test_case in test_cases:
        try:
            exec(test_case + "\n", namespace, namespace)
            passed_tests += 1
        except Exception:
            if failure_trace is None:
                failure_trace = traceback.format_exc()
    return passed_tests, len(test_cases), failure_trace


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

    def __init__(self, records: list[dict[str, Any]], reward_mode: str = "v2") -> None:
        self.records = records
        self.reward_mode = reward_mode
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
        cleaned_solution = clean_generated_solution(generated_solution)
        aligned_solution = align_entry_point(
            generated_solution=cleaned_solution,
            entry_point=str(self.current_record["entry_point"]),
        )

        try:
            exec(aligned_solution + "\n", namespace, namespace)
        except Exception:
            test_code = str(self.current_record["test_code"])
            info = {
                "passed": False,
                "passed_tests": 0,
                "total_tests": 1 if uses_humaneval_check(test_code) else len(extract_asserts(test_code)),
                "error_type": "generation_execution_error",
                "content": traceback.format_exc(),
                "reward_components": {
                    "executable": 0.0,
                    "entry_point": 0.0,
                    "ast": 0.0,
                    "signature": 0.0,
                    "test_pass_ratio": 0.0,
                    "full_pass": 0.0,
                },
            }
            return {"task_id": self.current_record["task_id"]}, 0.0, True, info

        passed_tests, total_tests, failure_trace = execute_test_code(
            namespace=namespace,
            record=self.current_record,
        )
        reward, reward_components = compute_reward(
            record=self.current_record,
            namespace=namespace,
            cleaned_solution=cleaned_solution,
            aligned_solution=aligned_solution,
            passed_tests=passed_tests,
            total_tests=total_tests,
            execution_ok=True,
            reward_mode=self.reward_mode,
        )
        passed = passed_tests == total_tests
        info = {
            "passed": passed,
            "passed_tests": passed_tests,
            "total_tests": total_tests,
            "error_type": None if passed else "partial_or_failed_tests",
            "content": "" if passed else (failure_trace or ""),
            "reward_components": reward_components,
        }
        return {"task_id": self.current_record["task_id"]}, reward, True, info


def compute_batch_advantages(rewards: list[float]) -> list[float]:
    if not rewards:
        return []
    baseline = sum(rewards) / len(rewards)
    return [round(reward - baseline, 6) for reward in rewards]
