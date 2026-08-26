#!/usr/bin/env python3
"""评测报告实体注册表、展示名称与定价配置。"""

from __future__ import annotations

import logging
import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


LOGGER = logging.getLogger(__name__)
SUPPORTED_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PricingTier:
    tier_id: str
    input_uncached: Decimal
    input_cached: Decimal
    output: Decimal
    cache_write: Decimal | None = None
    min_input_tokens_per_request: int | None = None
    max_input_tokens_per_request: int | None = None


@dataclass(frozen=True)
class PricingProfile:
    profile_id: str
    effective_from: date
    currency: str
    unit_tokens: int
    tiers: tuple[PricingTier, ...]


@dataclass(frozen=True)
class BillableUsage:
    input_uncached_tokens: int
    input_cached_tokens: int
    cache_write_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class RequestUsage:
    input_uncached_tokens: int
    input_cached_tokens: int
    output_tokens: int
    cache_write_tokens: int = 0

    @property
    def total_input_tokens(self) -> int:
        return (
            self.input_uncached_tokens
            + self.input_cached_tokens
            + self.cache_write_tokens
        )


@dataclass(frozen=True)
class CostEstimate:
    usd: Decimal | None
    profile_id: str | None
    status: str
    reason: str = ""


def _parse_date(value: Any, field_name: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 不是合法的 YYYY-MM-DD 日期: {value}") from exc


def _select_dated_record(
    records: Sequence[Mapping[str, Any]],
    target_date: date,
    label: str,
) -> Mapping[str, Any]:
    dated: list[tuple[date, Mapping[str, Any]]] = []
    seen_dates: set[date] = set()
    for record in records:
        effective_from = _parse_date(record.get("effective_from"), f"{label}.effective_from")
        if effective_from in seen_dates:
            raise ValueError(f"{label} 存在重复生效日期: {effective_from.isoformat()}")
        seen_dates.add(effective_from)
        if effective_from <= target_date:
            dated.append((effective_from, record))
    if not dated:
        raise ValueError(f"{label} 在 {target_date.isoformat()} 没有可用配置")
    return max(dated, key=lambda item: item[0])[1]


def _optional_int(record: Mapping[str, Any], key: str) -> int | None:
    value = record.get(key)
    return None if value is None else int(value)


@dataclass(frozen=True)
class EntityRegistry:
    models: Mapping[str, Mapping[str, Any]]
    harnesses: Mapping[str, Mapping[str, Any]]
    exchange_rates: Mapping[str, tuple[Mapping[str, Any], ...]]

    def model_display(self, model_id: str) -> str:
        return self._display(self.models, "model", model_id)

    def harness_display(self, harness_id: str) -> str:
        return self._display(self.harnesses, "harness", harness_id)

    def harness_canonical(self, harness_id: str) -> str:
        item = self.harnesses.get(harness_id) or {}
        return str(item.get("canonical_id") or harness_id).strip()

    @staticmethod
    def _display(
        entities: Mapping[str, Mapping[str, Any]],
        entity_type: str,
        entity_id: str,
    ) -> str:
        item = entities.get(entity_id) or {}
        value = str(item.get("display_name") or "").strip()
        if value:
            return value
        LOGGER.warning("%s %s 缺少 display_name，回退原始 ID", entity_type, entity_id)
        return entity_id

    def pricing_profile(self, model_id: str, pricing_date: date) -> PricingProfile:
        model = self.models.get(model_id)
        if not model:
            raise ValueError(f"模型 {model_id} 未配置定价")
        profiles = model.get("pricing_profiles") or []
        record = _select_dated_record(profiles, pricing_date, f"模型 {model_id} 定价档案")
        tiers = tuple(
            PricingTier(
                tier_id=str(tier["id"]),
                input_uncached=Decimal(str(tier["input_uncached"])),
                input_cached=Decimal(str(tier["input_cached"])),
                output=Decimal(str(tier["output"])),
                cache_write=(
                    Decimal(str(tier["cache_write"]))
                    if tier.get("cache_write") is not None
                    else None
                ),
                min_input_tokens_per_request=_optional_int(
                    tier, "min_input_tokens_per_request"
                ),
                max_input_tokens_per_request=_optional_int(
                    tier, "max_input_tokens_per_request"
                ),
            )
            for tier in record.get("tiers") or []
        )
        if not tiers:
            raise ValueError(f"模型 {model_id} 定价档案没有 tiers")
        unit_tokens = int(record.get("unit_tokens") or 0)
        if unit_tokens <= 0:
            raise ValueError(f"模型 {model_id} 定价档案 unit_tokens 必须大于 0")
        return PricingProfile(
            profile_id=str(record["id"]),
            effective_from=_parse_date(
                record.get("effective_from"), f"模型 {model_id} 定价档案.effective_from"
            ),
            currency=str(record["currency"]).upper(),
            unit_tokens=unit_tokens,
            tiers=tiers,
        )

    def cny_per_usd(self, pricing_date: date) -> Decimal:
        records = self.exchange_rates.get("CNY") or ()
        record = _select_dated_record(records, pricing_date, "CNY 汇率")
        rate = Decimal(str(record.get("cny_per_usd")))
        if rate <= 0:
            raise ValueError("CNY 汇率必须大于 0")
        return rate


def load_registry(path: Path) -> EntityRegistry:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"不支持的 entities schema_version: {data.get('schema_version')}")
    return EntityRegistry(
        models=data.get("models") or {},
        harnesses=data.get("harnesses") or {},
        exchange_rates={
            currency: tuple(records)
            for currency, records in (data.get("exchange_rates") or {}).items()
        },
    )


def normalize_billable_usage(usage: Mapping[str, Any]) -> BillableUsage:
    input_tokens = int(usage.get("input_tokens") or 0)
    cached = int(usage.get("cache_read_tokens") or 0)
    cache_write = int(usage.get("cache_write_tokens") or 0)
    output = int(usage.get("output_tokens") or 0)
    total = int(usage.get("total_tokens") or 0)
    values = (input_tokens, cached, cache_write, output, total)
    if any(value < 0 for value in values):
        raise ValueError("usage.json 包含负数 token")
    if total == input_tokens + output:
        uncached = input_tokens - cached - cache_write
    elif total == input_tokens + cached + cache_write + output:
        uncached = input_tokens
    else:
        raise ValueError("无法判断 usage.json 的 input_tokens 缓存语义")
    if uncached < 0:
        raise ValueError("缓存 token 超过输入 token")
    return BillableUsage(uncached, cached, cache_write, output)


def _select_tier(profile: PricingProfile, request_input_tokens: int) -> PricingTier:
    matches = []
    for tier in profile.tiers:
        if (
            tier.min_input_tokens_per_request is not None
            and request_input_tokens < tier.min_input_tokens_per_request
        ):
            continue
        if (
            tier.max_input_tokens_per_request is not None
            and request_input_tokens > tier.max_input_tokens_per_request
        ):
            continue
        matches.append(tier)
    if len(matches) != 1:
        raise ValueError(
            f"定价档案 {profile.profile_id} 无法为单请求输入 "
            f"{request_input_tokens} 唯一选择档位"
        )
    return matches[0]


def _cost_in_profile_currency(
    profile: PricingProfile,
    tier: PricingTier,
    usage: BillableUsage,
) -> Decimal | None:
    if usage.cache_write_tokens and tier.cache_write is None:
        return None
    numerator = (
        Decimal(usage.input_uncached_tokens) * tier.input_uncached
        + Decimal(usage.input_cached_tokens) * tier.input_cached
        + Decimal(usage.output_tokens) * tier.output
    )
    if usage.cache_write_tokens:
        numerator += Decimal(usage.cache_write_tokens) * tier.cache_write
    return numerator / Decimal(profile.unit_tokens)


def _to_usd(
    registry: EntityRegistry,
    pricing_date: date,
    currency: str,
    amount: Decimal,
) -> Decimal:
    if currency == "USD":
        return amount
    if currency == "CNY":
        return amount / registry.cny_per_usd(pricing_date)
    raise ValueError(f"不支持的定价币种: {currency}")


def estimate_cost_usd(
    registry: EntityRegistry,
    model_id: str,
    pricing_date: date,
    usage: BillableUsage,
    request_input_tokens: int | None,
) -> CostEstimate:
    try:
        profile = registry.pricing_profile(model_id, pricing_date)
    except ValueError as exc:
        return CostEstimate(None, None, "unavailable", str(exc))
    if len(profile.tiers) == 1:
        tier = profile.tiers[0]
    elif request_input_tokens is None:
        return CostEstimate(
            None,
            profile.profile_id,
            "unavailable",
            "分档定价缺少逐请求输入 token",
        )
    else:
        try:
            tier = _select_tier(profile, request_input_tokens)
        except ValueError as exc:
            return CostEstimate(None, profile.profile_id, "unavailable", str(exc))
    amount = _cost_in_profile_currency(profile, tier, usage)
    if amount is None:
        return CostEstimate(
            None,
            profile.profile_id,
            "unavailable",
            "存在缓存写入 token，但定价档位缺少缓存写入单价",
        )
    try:
        usd = _to_usd(registry, pricing_date, profile.currency, amount)
    except ValueError as exc:
        return CostEstimate(None, profile.profile_id, "unavailable", str(exc))
    return CostEstimate(usd, profile.profile_id, "estimated")


def estimate_request_costs_usd(
    registry: EntityRegistry,
    model_id: str,
    pricing_date: date,
    requests: Sequence[RequestUsage],
) -> CostEstimate:
    try:
        profile = registry.pricing_profile(model_id, pricing_date)
    except ValueError as exc:
        return CostEstimate(None, None, "unavailable", str(exc))
    total = Decimal(0)
    for request in requests:
        try:
            tier = (
                profile.tiers[0]
                if len(profile.tiers) == 1
                else _select_tier(profile, request.total_input_tokens)
            )
        except ValueError as exc:
            return CostEstimate(None, profile.profile_id, "unavailable", str(exc))
        usage = BillableUsage(
            request.input_uncached_tokens,
            request.input_cached_tokens,
            request.cache_write_tokens,
            request.output_tokens,
        )
        amount = _cost_in_profile_currency(profile, tier, usage)
        if amount is None:
            return CostEstimate(
                None,
                profile.profile_id,
                "unavailable",
                "存在缓存写入 token，但定价档位缺少缓存写入单价",
            )
        total += amount
    try:
        usd = _to_usd(registry, pricing_date, profile.currency, total)
    except ValueError as exc:
        return CostEstimate(None, profile.profile_id, "unavailable", str(exc))
    return CostEstimate(usd, profile.profile_id, "estimated")


def _require_nonnegative(values: Mapping[str, int], source: str) -> None:
    negative = {key: value for key, value in values.items() if value < 0}
    if negative:
        raise ValueError(f"{source} 包含负数 token: {negative}")


def extract_astroncode_requests(run_dir: Path) -> list[RequestUsage]:
    transcript = next(
        (path for path in (run_dir / "chat.jsonl", run_dir / "chat_openclaw.jsonl")
         if path.is_file()),
        None,
    )
    if transcript is None:
        raise FileNotFoundError(f"AstronCode run 缺少 chat.jsonl: {run_dir}")
    requests: list[RequestUsage] = []
    seen_cumulative: set[str] = set()
    for line_number, line in enumerate(
        transcript.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = event.get("payload") or {}
        if payload.get("type") != "token_count":
            continue
        info = payload.get("info") or {}
        last = info.get("last_token_usage") or {}
        if not last:
            continue
        cumulative = info.get("total_token_usage") or last
        cumulative_key = json.dumps(cumulative, sort_keys=True, ensure_ascii=False)
        if cumulative_key in seen_cumulative:
            continue
        seen_cumulative.add(cumulative_key)
        input_tokens = int(last.get("input_tokens") or 0)
        cached = int(last.get("cached_input_tokens") or 0)
        output = int(last.get("output_tokens") or 0)
        cache_write = int(last.get("cache_write_tokens") or 0)
        values = {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached,
            "cache_write_tokens": cache_write,
            "output_tokens": output,
        }
        _require_nonnegative(values, f"{transcript}:{line_number}")
        uncached = input_tokens - cached - cache_write
        if uncached < 0:
            raise ValueError(f"{transcript}:{line_number} 缓存 token 超过输入 token")
        requests.append(RequestUsage(uncached, cached, output, cache_write))
    return requests


def _dsh_usage_int(value: Any, source: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        raise ValueError(f"{source} token 必须是非负整数")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source} token 必须是非负整数") from exc
    if number < 0 or (isinstance(value, float) and not value.is_integer()):
        raise ValueError(f"{source} token 必须是非负整数")
    return number


def extract_deepseek_harness_requests(run_dir: Path) -> list[RequestUsage]:
    session_root = run_dir / "dsh_sessions"
    if not session_root.is_dir() and (run_dir / "session.jsonl").is_file():
        session_root = run_dir
    session_files = sorted(session_root.rglob("session.jsonl"))
    if not session_files:
        raise FileNotFoundError(f"DeepSeek Harness run 缺少 dsh_sessions/session.jsonl: {run_dir}")

    requests: list[RequestUsage] = []
    for session_file in session_files:
        for line_number, line in enumerate(
            session_file.read_text(encoding="utf-8", errors="replace").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{session_file}:{line_number} 不是合法 JSON") from exc
            if not isinstance(event, dict) or event.get("type") != "assistant/message":
                continue
            data = event.get("data")
            usage = data.get("usage") if isinstance(data, dict) else None
            if not isinstance(usage, dict):
                continue
            source = f"{session_file}:{line_number}"
            requests.append(RequestUsage(
                _dsh_usage_int(usage.get("inputTokens"), f"{source}.inputTokens"),
                _dsh_usage_int(usage.get("cacheReadTokens"), f"{source}.cacheReadTokens"),
                _dsh_usage_int(usage.get("outputTokens"), f"{source}.outputTokens"),
                _dsh_usage_int(usage.get("cacheWriteTokens"), f"{source}.cacheWriteTokens"),
            ))
    if not requests:
        raise ValueError(f"DeepSeek Harness run 没有逐请求 token usage: {run_dir}")
    return requests


def extract_opencode_requests(run_dir: Path) -> list[RequestUsage]:
    database = next(
        (path for path in (run_dir / "opencode.db", run_dir / "opencode_data/opencode.db")
         if path.is_file()),
        None,
    )
    if database is None:
        raise FileNotFoundError(f"OpenCode run 缺少 opencode.db: {run_dir}")
    requests: list[RequestUsage] = []
    with sqlite3.connect(database) as connection:
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(part)").fetchall()
        }
        order_by = "time_created, id" if "time_created" in columns else "id"
        rows = connection.execute(f"SELECT data FROM part ORDER BY {order_by}").fetchall()
    for row_number, (raw_data,) in enumerate(rows, start=1):
        try:
            data = json.loads(raw_data)
        except (TypeError, json.JSONDecodeError):
            continue
        if data.get("type") != "step-finish":
            continue
        tokens = data.get("tokens") or {}
        cache = tokens.get("cache") or {}
        values = {
            "input": int(tokens.get("input") or 0),
            "cache_read": int(cache.get("read") or 0),
            "cache_write": int(cache.get("write") or 0),
            "output": int(tokens.get("output") or 0),
            "reasoning": int(tokens.get("reasoning") or 0),
        }
        _require_nonnegative(values, f"{database}:part row {row_number}")
        requests.append(RequestUsage(
            values["input"],
            values["cache_read"],
            values["output"] + values["reasoning"],
            values["cache_write"],
        ))
    return requests
