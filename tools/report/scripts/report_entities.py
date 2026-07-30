#!/usr/bin/env python3
"""评测报告实体注册表、展示名称与定价配置。"""

from __future__ import annotations

import logging
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
