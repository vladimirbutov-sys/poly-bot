"""
core/iran_evaluator.py — Claude API оценка сигнала для Iran-бота

Оценивает важность новости по конфликту Иран-США.
Без привязки к конкретным рынкам Polymarket (экономия токенов).

Оптимизация: один вызов Haiku вместо Haiku pre-screen + Sonnet eval.
"""
import asyncio
import json
import logging
import time

import httpx

from core.config import ANTHROPIC_API_KEY

logger = logging.getLogger("iran_evaluator")

IRAN_SYSTEM_PROMPT = """You are a factual news classifier. Your ONLY task: determine whether a news item signals ESCALATION or DE-ESCALATION of the Iran-US military conflict.

You do NOT interpret, predict, or editorialize. You classify what HAS happened or what HAS been officially announced.

WHAT COUNTS AS ESCALATION (direct indicators only):
- Confirmed military strikes, attacks, or use of force by any party
- Official ultimatums, threats of imminent military action with deadlines
- Confirmed troop/fleet deployments toward combat positions
- Closure or blockade of Strait of Hormuz (confirmed, not threatened)
- Official declaration of war or military operations
- Confirmed infrastructure attacks (power plants, oil facilities, desalination)

WHAT COUNTS AS DE-ESCALATION (direct indicators only):
- Official ceasefire announcement or agreement
- Confirmed start of direct negotiations between parties
- Official withdrawal of ultimatums or extension of deadlines
- Confirmed military stand-down or withdrawal orders
- Official diplomatic agreement (nuclear deal, ceasefire terms)
- Reopening of Strait of Hormuz (confirmed)

WHAT DOES NOT COUNT (ignore these — classify as LOW):
- Pundit opinions, think-tank analysis, speculation
- "Sources say", "may", "could", "considering", "weighing options"
- Routine diplomatic statements, sanctions, UN speeches
- Historical comparisons, background explainers
- Social media reactions, polls, market commentary
- News not directly about Iran-US military conflict

CONFIDENCE LEVELS:
- HIGH: a confirmed escalation or de-escalation event from an official or Tier 1 source. The event HAS happened or HAS been officially announced with a specific commitment.
- MEDIUM: a credible report of escalation/de-escalation from Tier 1-2 source, but not yet confirmed by multiple sources. Or: confirmed event but with ambiguous impact.
- LOW: everything else — speculation, indirect signals, routine news, unrelated topics.

DIRECTION field: classify as "escalation", "de-escalation", or "neutral".

Be MAXIMALLY conservative. Default to LOW. Only upgrade when the evidence is unambiguous.

Respond ONLY with valid JSON, no markdown."""

IRAN_USER_PROMPT = """NEWS:
Source: {source_name} (Tier {tier}, {topic})
Language: {lang}
Time: {timestamp}
Text: {text}

Classify this news item. Return JSON:
{{
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "direction": "escalation" | "de-escalation" | "neutral",
  "topic_key": "short_snake_case_topic_id (e.g. us_strikes_tehran, ceasefire_announced, hormuz_reopened). Same event from different sources MUST produce the same topic_key.",
  "reasoning": "1-2 sentences: what specific event happened and why it is escalation/de-escalation. In Russian.",
  "summary": "1-sentence factual news summary in Russian. No interpretation."
}}"""


class IranEvaluator:
    """Claude API evaluator для Iran-бота — один вызов Haiku на сообщение."""

    def __init__(self):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._results: dict[str, asyncio.Future] = {}
        self._counter = 0
        self._running = False
        self._min_interval = 1.0
        self._eval_count = 0

    async def start_worker(self):
        self._running = True
        logger.info("Iran evaluator worker started")
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
                logger.error(f"Iran evaluator error: {e}")
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
        source_url: str = "",
    ) -> dict | None:
        self._counter += 1
        request_id = f"iran_req_{self._counter}"

        future = asyncio.get_event_loop().create_future()
        self._results[request_id] = future

        priority = max(0, tier - 1)

        await self._queue.put((
            priority, self._counter, request_id,
            {
                "text": text,
                "source_name": source_name,
                "tier": tier,
                "topic": topic,
                "lang": lang,
                "timestamp": timestamp,
                "source_url": source_url,
            },
        ))

        qsize = self._queue.qsize()
        if qsize > 3:
            logger.info(f"Queue size: {qsize}, priority: {priority}")

        try:
            result = await asyncio.wait_for(future, timeout=60.0)
        except asyncio.TimeoutError:
            logger.warning(f"Evaluation timed out for {source_name}")
            result = None
        finally:
            self._results.pop(request_id, None)

        return result

    async def _call_claude(self, **kwargs) -> dict | None:
        """Один вызов Haiku: оценка + классификация."""
        prompt = IRAN_USER_PROMPT.format(
            source_name=kwargs["source_name"],
            tier=kwargs["tier"],
            topic=kwargs["topic"],
            lang=kwargs["lang"],
            timestamp=kwargs["timestamp"],
            text=kwargs["text"][:1500],
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
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 400,
                        "system": IRAN_SYSTEM_PROMPT,
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
            result["_source_url"] = kwargs.get("source_url", "")

            self._eval_count += 1
            if self._eval_count % 20 == 0:
                logger.info(f"Haiku evaluations: {self._eval_count} total")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Claude JSON parse error: {e}")
            return None
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            return None
