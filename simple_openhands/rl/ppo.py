"""PPO helpers for single-step code-generation updates."""

from __future__ import annotations

from typing import Any

import torch
from torch import nn


class ScalarValueHead(nn.Module):
    """A minimal scalar value head over pooled response hidden states."""

    def __init__(self, hidden_size: int, dropout: float = 0.0) -> None:
        super().__init__()
        self.dropout = nn.Dropout(dropout)
        self.value = nn.Linear(hidden_size, 1)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        hidden_states = self.dropout(hidden_states).to(self.value.weight.dtype)
        return self.value(hidden_states).squeeze(-1)


def compute_single_step_gae(
    rewards: list[float], values: list[float], gamma: float = 1.0, lam: float = 1.0
) -> tuple[list[float], list[float]]:
    """Single-step GAE/return helper.

    For the current project each prompt is a one-step episode, so:
    - return = reward
    - advantage = reward - value
    gamma / lam are accepted to keep the interface PPO-shaped.
    """

    del gamma, lam
    returns = [float(reward) for reward in rewards]
    advantages = [float(reward) - float(value) for reward, value in zip(rewards, values, strict=True)]
    return advantages, returns


def tensor_mean(items: list[torch.Tensor]) -> torch.Tensor:
    if not items:
        raise ValueError("tensor_mean requires at least one tensor")
    return torch.stack(items).mean()


def to_device(module: nn.Module, model: Any) -> nn.Module:
    return module.to(model.device)
