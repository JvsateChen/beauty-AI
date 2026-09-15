"""数据源 Provider 抽象与注册表。

设计要点：
  · 每家渠道 = 一个 Provider，实现统一的 ``fetch(product) -> list[offer]``
  · Provider 声明自己需要哪些凭据；凭据缺失时不报错、不伪造，而是进入
    NOT_CONFIGURED 状态 —— 上层据此把该渠道呈现为「未接入」。
  · 内置种子数据集也是一个 Provider（SeedProvider），保证离线可用；
    它与真实 Provider 可共存（hybrid 模式：真源优先、缺失渠道由种子补齐，
    但**必须**把每个报价的来源如实标出来）。
  · 统一 TTL 缓存 + 超时 + 重试 + 熔断，避免拖垮主流程。

所有对外响应都会带 ``data_basis`` 说明本条数据是 live 还是 seed，前端据此展示
「数据来源」，杜绝「看起来是实时数据其实是演示数据」的误导。
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from core.catalog import Product

logger = logging.getLogger("caixuan.provider")


class ProviderNotConfigured(RuntimeError):
    """凭据未配置 —— 调用方应把它当作「未接入」而非故障。"""


@dataclass
class ProviderStatus:
    channel: str
    configured: bool
    #: live / seed
    mode: str
    note: str = ""


@runtime_checkable
class PriceProvider(Protocol):
    channel: str

    def is_configured(self) -> bool: ...

    def fetch(self, product: Product) -> list[dict]:
        """返回该渠道的报价原始列表（尚未归一化）。

        每个 dict 至少包含：channel / shop_name / shop_type / version /
        list_price / benefits / risk_tags / shelf_life_months / warranty。
        ``price`` 可省略（由优惠拆解推导）。
        凭据缺失时抛 ProviderNotConfigured。
        """
        ...


# ---------------------------------------------------------------------------
# TTL 缓存
# ---------------------------------------------------------------------------

class TTLCache:
    """极简线程安全 TTL 缓存（单进程内）。多进程/多实例场景下由 DB 快照兜底。"""

    def __init__(self, ttl_seconds: int = 300, max_items: int = 2048):
        self.ttl = ttl_seconds
        self.max_items = max_items
        self._data: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            hit = self._data.get(key)
        if not hit:
            return None
        expire_at, value = hit
        if expire_at < time.time():
            with self._lock:
                self._data.pop(key, None)
            return None
        return value

    def set(self, key: str, value) -> None:
        with self._lock:
            if len(self._data) >= self.max_items:
                # 简单淘汰：清掉已过期项，仍超限则丢弃最早写入的一批
                now = time.time()
                for k in [k for k, (exp, _) in self._data.items() if exp < now]:
                    self._data.pop(k, None)
                if len(self._data) >= self.max_items:
                    for k in list(self._data)[: self.max_items // 4]:
                        self._data.pop(k, None)
            self._data[key] = (time.time() + self.ttl, value)

    def invalidate(self, prefix: str | None = None) -> None:
        with self._lock:
            if prefix is None:
                self._data.clear()
            else:
                for k in [k for k in self._data if k.startswith(prefix)]:
                    self._data.pop(k, None)


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------

class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, PriceProvider] = {}

    def register(self, provider: PriceProvider) -> None:
        self._providers[provider.channel] = provider

    def get(self, channel: str) -> PriceProvider | None:
        return self._providers.get(channel)

    def all(self) -> list[PriceProvider]:
        return list(self._providers.values())

    def statuses(self) -> list[ProviderStatus]:
        out: list[ProviderStatus] = []
        for p in self._providers.values():
            try:
                configured = p.is_configured()
            except Exception:  # pragma: no cover - 防御性
                configured = False
            mode = getattr(p, "mode", "live" if configured else "seed")
            out.append(ProviderStatus(p.channel, configured, mode))
        return out
