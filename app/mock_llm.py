from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from .incidents import STATE
from .tracing import get_langfuse_client, observe

# USD per 1M tokens. Shared with LabAgent._estimate_cost so the generation cost in
# the trace matches cost_usd in the structured log.
PRICE_PER_MTOK_USD = {"input": 3.0, "output": 15.0}


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class FakeResponse:
    text: str
    usage: FakeUsage
    model: str
    ttft_ms: int


class FakeLLM:
    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model

    # Nested under the agent root inside propagate_attributes(prompt=...), so the
    # managed prompt is linked automatically. The compiled prompt contains the raw
    # user message, so input/output are not captured.
    @observe(name="llm-generation", as_type="generation", capture_input=False, capture_output=False)
    def generate(self, prompt: str) -> FakeResponse:
        started = time.perf_counter()
        time.sleep(0.05)  # mô phỏng thời điểm token đầu tiên sẵn sàng
        ttft_ms = int((time.perf_counter() - started) * 1000)
        first_token_at = datetime.now(timezone.utc)
        time.sleep(0.10)
        input_tokens = max(20, len(prompt) // 4)
        output_tokens = random.randint(80, 180)
        if STATE["cost_spike"]:
            output_tokens *= 4
        answer = (
            "Starter answer. You should improve this output logic and add better quality checks. "
            "Use retrieved context and keep responses concise."
        )
        get_langfuse_client().update_current_generation(
            model=self.model,
            completion_start_time=first_token_at,
            usage_details={"input": input_tokens, "output": output_tokens},
            cost_details={
                "input": input_tokens / 1_000_000 * PRICE_PER_MTOK_USD["input"],
                "output": output_tokens / 1_000_000 * PRICE_PER_MTOK_USD["output"],
            },
        )
        return FakeResponse(
            text=answer,
            usage=FakeUsage(input_tokens, output_tokens),
            model=self.model,
            ttft_ms=ttft_ms,
        )
