"""
core/evaluator.py — Claude API оценка сигнала с приоритетной очередью

Tier 1 (официальные заявления) обрабатываются первыми,
даже если в очереди 30 запросов от экзит-поллов.
"""
import asyncio
import json
import logging
import time

import httpx

from core.config import ANTHROPIC_API_KEY

logger = logging.getLogger("evaluator")

SYSTEM_PROMPT = """You are a Polymarket trading signal analyst. Assess whether a breaking news item will cause a PRICE SPIKE on a specific Polymarket market.

CRITICAL CONTEXT:
- The trader profits from PRICE SPIKES caused by news, NOT from market resolution
- A signal is valuable if the news will move the market price >5 percentage points within minutes to hours
- The Polymarket trader base is primarily English-speaking — they react to English media with a DELAY of 30min-6hrs after non-English sources

RULES:
- Be CONSERVATIVE. Better to miss a signal than send a false one
- HIGH confidence: official government source AND directly maps to a specific market
- MEDIUM confidence: credible source AND likely affects a market
- LOW: everything else

Respond ONLY with valid JSON, no markdown."""

USER_PROMPT_TEMPLATE = """NEWS:
Source: {source_name} (Tier {tier}, {topic})
Language: {lang}
Time: {timestamp}
Text: {text}

ACTIVE MARKETS:
{markets_summary}

Return JSON:
{{
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "relevant_market_slug": "slug or null",
  "relevant_market_title": "title or null",
  "direction": "YES_UP" | "YES_DOWN" | null,
  "current_price_pct": <number or null>,
  "expected_spike_pct": <number or null>,
  "estimated_window_minutes": <number or null>,
  "reasoning": "1-2 sentences in Russian",
  "summary": "1-sentence news summary in Russian"
}}"""


class PriorityEvaluator:
    """
    Claude API evaluator с приоритетной очередью.

    Tier 1 → priority 0 (обрабатывается первым)
    Tier 2 → priority 1
    Tier 3 → priority 2
    Tier 4 → priority 3 (выборы, может подождать)
    """

    def __init__(self):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._results: dict[str, asyncio.Future] = {}
        self._counter = 0  # для стабильной сортировки при одинаковом приоритете
        self._running = False
        self._min_interval = 1.5  # секунд между запросами (rate limit)

    async def start_worker(self):
        """Запустить воркер, обрабатывающий очередь."""
        self._running = True
        logger.info("Evaluator worker started")
        while self._running:
            try:
                priority, counter, request_id, kwargs = await asyncio.wait_for(
                    self._queue.get(), timeout=5.0
                )
            except asyncio.TimeoutError:
                continue

            try:
                result = await self._call_claude(**kwargs)
                if request_id in self._results:
                    self._results[request_id].set_result(result)
            except Exception as e:
                logger.error(f"Evaluator worker error: {e}")
                if request_id in self._results:
                    self._results[request_id].set_result(None)

            await asyncio.sleep(self._min_interval)

    async def evaluate(
        self,
        text: str,
        source_name: str,
        tier: int,
        topic: str,
        lang: str,
        timestamp: str,
        markets_summary: str,
    ) -> dict | None:
        """
        Поставить запрос в очередь и дождаться результата.
        Tier 1 обрабатывается раньше Tier 4.
        """
        self._counter += 1
        request_id = f"req_{self._counter}"

        future = asyncio.get_event_loop().create_future()
        self._results[request_id] = future

        # Priority: tier 1 → 0, tier 2 → 1, etc.
        priority = max(0, tier - 1)

        await self._queue.put((
            priority,
            self._counter,
            request_id,
            {
                "text": text,
                "source_name": source_name,
                "tier": tier,
                "topic": topic,
                "lang": lang,
                "timestamp": timestamp,
                "markets_summary": markets_summary,
            },
        ))

        qsize = self._queue.qsize()
        if qsize > 3:
            logger.info(f"Queue size: {qsize}, this request priority: {priority}")

        try:
            result = await asyncio.wait_for(future, timeout=60.0)
        except asyncio.TimeoutError:
            logger.warning(f"Evaluation timed out for {source_name}")
            result = None
        finally:
            self._results.pop(request_id, None)

        return result

    async def _call_claude(self, **kwargs) -> dict | None:
        """Вызов Claude API."""
        prompt = USER_PROMPT_TEMPLATE.format(
            source_name=kwargs["source_name"],
            tier=kwargs["tier"],
            topic=kwargs["topic"],
            lang=kwargs["lang"],
            timestamp=kwargs["timestamp"],
            text=kwargs["text"][:2000],
            markets_summary=kwargs["markets_summary"],
        )

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 500,
                        "system": SYSTEM_PROMPT,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            content = data.get("content", [{}])[0].get("text", "").strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0]

            result = json.loads(content)
            if "confidence" not in result:
                return None

            result["_source"] = kwargs["source_name"]
            result["_timestamp"] = kwargs["timestamp"]
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Claude JSON parse error: {e}")
            return None
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            return None
