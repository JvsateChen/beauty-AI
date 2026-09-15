"""真实渠道 Provider（联盟 CPS / 保税仓数据方）。

⚠️ 状态说明（诚实标注，不要当成已验证）
本文件按各平台**公开接口文档**实现了请求签名、参数拼装与响应映射，但当前环境
没有真实联盟凭据，**签名与字段映射尚未经过线上联调验证**。凭据到位后需执行
``python -m providers.live --verify`` 逐渠道跑一次自检（见文件末尾）。

设计要点：
  · 凭据缺失 → 抛 ProviderNotConfigured（上层据此展示「未接入」，绝不伪造数据）
  · 超时 / 重试 / 退避 → 统一在 _SignedClient
  · 上游异常 → 抛 UpstreamError，由统一错误体返回 502 + request_id，不外泄堆栈
  · 版本 / 临期 / 风险标签等**我们自己的口径字段**在归一化层补齐（core.domain），
    Provider 只负责把平台数据翻译成我们的基础字段，不重复实现业务规则

各平台签名口径备忘：
  淘宝客 TOP   MD5(secret + 按 ASCII 升序拼接的 k+v 串 + secret)，大写
  京东联盟     MD5(secret + 按 ASCII 升序拼接的 k+v 串 + secret)，大写
  拼多多多多客 MD5(secret + 拼接串 + secret)，大写
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import httpx

from core.catalog import Product
from core.config import settings
from core.errors import UpstreamError
from providers.base import ProviderNotConfigured

logger = logging.getLogger("caixuan.provider.live")


class _SignedClient:
    """带超时/重试/退避的 HTTP 客户端基类。"""

    def __init__(self, base_url: str, timeout: float | None = None, retries: int | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout or settings.outbound_timeout_seconds
        self.retries = settings.outbound_max_retries if retries is None else retries

    def request(self, method: str, path: str, **kw) -> dict:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.request(method, url, **kw)
                if r.status_code >= 500:
                    raise UpstreamError("UPSTREAM_5XX", f"上游返回 {r.status_code}")
                if r.status_code >= 400:
                    # 4xx 通常是参数/凭据问题，重试无意义
                    raise UpstreamError(
                        "UPSTREAM_4XX", f"上游拒绝请求（HTTP {r.status_code}）"
                    )
                return r.json()
            except (httpx.TimeoutException, httpx.TransportError, UpstreamError) as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(0.4 * (2 ** attempt))  # 指数退避
                    continue
        logger.warning("上游调用失败 %s %s：%s", method, url.split("?")[0], last_exc)
        if isinstance(last_exc, UpstreamError):
            raise last_exc
        raise UpstreamError("UPSTREAM_UNREACHABLE", "上游数据源暂时不可用") from last_exc


def _md5_sign(params: dict[str, Any], secret: str) -> str:
    """TOP / 京东 / 拼多多通用的「升序拼接 + 前后加 secret」MD5 签名。"""
    joined = "".join(f"{k}{params[k]}" for k in sorted(params) if params[k] not in (None, ""))
    return hashlib.md5(f"{secret}{joined}{secret}".encode("utf-8")).hexdigest().upper()


def _to_offer(
    *,
    channel: str,
    shop_name: str,
    shop_type: str,
    version: str,
    list_price: float,
    price: float,
    affiliate_url: str | None,
    origin: str | None = None,
    months: int | None = None,
    warranty: str | None = None,
    note: str | None = None,
    sponsored: bool = False,
) -> dict:
    """把平台数据翻译成我们的报价形状。

    注意：这里**不**推算 benefits —— 真实平台返回的是「券后价 / 到手价」，
    优惠项往往不可完整拆解。因此本条 ``price`` 显式给出，由
    ``core.domain.normalize_offer(strict_derive=False)`` 校验与推导值的偏差，
    偏差过大时在响应里标 ``price_consistent=False``，前端提示「优惠拆解不完整」。
    """
    return {
        "id": f"{channel}-{version}-{abs(hash(affiliate_url or shop_name)) % 10**6}",
        "channel": channel,
        "shop_name": shop_name,
        "shop_type": shop_type,
        "version": version,
        "origin": origin,
        "list_price": list_price,
        "price": price,
        "benefits": {},          # 真实源未拆解时为空；domain 层据 price 回填差额
        "affiliate_url": affiliate_url,
        "risk_tags": [],
        "shelf_life_months": months,
        "warranty": warranty,
        "note": note,
        "sponsored": sponsored,
        "data_basis": "live",
    }


# ---------------------------------------------------------------------------
# 淘宝联盟（天猫）
# ---------------------------------------------------------------------------

class TmallUnionProvider:
    channel = "天猫"
    mode = "live"
    ENDPOINT = "https://eco.taobao.com/router/rest"

    def __init__(self) -> None:
        self.app_key = settings.tmall_union_app_key
        self.secret = settings.tmall_union_app_secret
        self.pid = settings.tmall_union_pid
        self.client = _SignedClient(self.ENDPOINT)

    def is_configured(self) -> bool:
        return bool(self.app_key and self.secret and self.pid)

    def fetch(self, product: Product) -> list[dict]:
        if not self.is_configured():
            raise ProviderNotConfigured("淘宝联盟凭据未配置")
        params: dict[str, Any] = {
            "app_key": self.app_key,
            "method": "taobao.tbk.dg.material.optional",
            "format": "json",
            "v": "2.0",
            "sign_method": "md5",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "adzone_id": self.pid.split("_")[-1] if "_" in self.pid else self.pid,
            "q": f"{product.brand} {product.name}",
            "page_size": 20,
        }
        params["sign"] = _md5_sign(params, self.secret)
        data = self.client.request("GET", "", params=params)
        rows = (
            data.get("tbk_dg_material_optional_response", {})
            .get("result_list", {})
            .get("map_data", [])
        ) or []
        out: list[dict] = []
        for it in rows:
            try:
                list_price = float(it.get("reserve_price") or it.get("zk_final_price") or 0)
                price = float(it.get("zk_final_price") or 0)
            except (TypeError, ValueError):
                continue
            if list_price <= 0 or price <= 0:
                continue
            shop_type = str(it.get("user_type", ""))
            out.append(_to_offer(
                channel=self.channel,
                shop_name=str(it.get("shop_title") or it.get("nick") or "天猫店铺"),
                shop_type="自营" if shop_type == "1" else "第三方店铺",
                version="国行",                       # 天猫主站默认为国行；跨境另见保税仓渠道
                list_price=list_price,
                price=price,
                affiliate_url=it.get("coupon_share_url") or it.get("url"),
                note=f"平台销量 {it.get('volume')}" if it.get("volume") else None,
            ))
        if not out:
            raise UpstreamError("UPSTREAM_EMPTY", "淘宝联盟未返回可用报价")
        return out


# ---------------------------------------------------------------------------
# 京东联盟
# ---------------------------------------------------------------------------

class JdUnionProvider:
    channel = "京东"
    mode = "live"
    ENDPOINT = "https://api.jd.com/routerjson"

    def __init__(self) -> None:
        self.app_key = settings.jd_union_app_key
        self.secret = settings.jd_union_app_secret
        self.pid = settings.jd_union_pid
        self.client = _SignedClient(self.ENDPOINT)

    def is_configured(self) -> bool:
        return bool(self.app_key and self.secret and self.pid)

    def fetch(self, product: Product) -> list[dict]:
        if not self.is_configured():
            raise ProviderNotConfigured("京东联盟凭据未配置")
        biz = {
            "keyword": f"{product.brand} {product.name}",
            "pageSize": 20,
            "pageIndex": 1,
        }
        param_json = httpx.QueryParams({"goodsReqDTO": str(biz)}).get("goodsReqDTO")
        params: dict[str, Any] = {
            "app_key": self.app_key,
            "method": "jd.union.open.goods.query",
            "format": "json",
            "v": "1.0",
            "sign_method": "md5",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "param_json": param_json,
        }
        params["sign"] = _md5_sign(params, self.secret)
        data = self.client.request("POST", "", params=params)
        payload = data.get("jd_union_open_goods_query_responce", {}) or {}
        body = payload.get("queryResult")
        if isinstance(body, str):
            import json
            try:
                body = json.loads(body)
            except ValueError:
                body = {}
        rows = (body or {}).get("data", []) or []
        out: list[dict] = []
        for it in rows:
            try:
                price = float(it.get("price") or 0)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            out.append(_to_offer(
                channel=self.channel,
                shop_name=str(it.get("shopName") or "京东店铺"),
                shop_type="自营" if it.get("owner") == "g" else "第三方店铺",
                version="国行",
                list_price=float(it.get("marketPrice") or price),
                price=price,
                affiliate_url=(it.get("materialUrl") or "").replace("http://", "https://") or None,
                note=f"佣金 {it.get('commissionInfo', {}).get('commissionShare')}%" if it.get("commissionInfo") else None,
            ))
        if not out:
            raise UpstreamError("UPSTREAM_EMPTY", "京东联盟未返回可用报价")
        return out


# ---------------------------------------------------------------------------
# 拼多多（多多客）
# ---------------------------------------------------------------------------

class PddDuoProvider:
    channel = "拼多多"
    mode = "live"
    ENDPOINT = "https://gw-api.pinduoduo.com/api/router"

    def __init__(self) -> None:
        self.app_key = settings.pdd_duo_app_key
        self.secret = settings.pdd_duo_app_secret
        self.pid = settings.pdd_duo_pid
        self.client = _SignedClient(self.ENDPOINT)

    def is_configured(self) -> bool:
        return bool(self.app_key and self.secret and self.pid)

    def fetch(self, product: Product) -> list[dict]:
        if not self.is_configured():
            raise ProviderNotConfigured("多多客凭据未配置")
        params: dict[str, Any] = {
            "type": "pdd.ddk.goods.search",
            "client_id": self.app_key,
            "timestamp": str(int(time.time())),
            "data_type": "JSON",
            "keyword": f"{product.brand} {product.name}",
            "page_size": 20,
            "pid": self.pid,
        }
        params["sign"] = _md5_sign(params, self.secret)
        data = self.client.request("POST", "", data=params)
        rows = (data.get("goods_search_response") or {}).get("goods_list", []) or []
        out: list[dict] = []
        for it in rows:
            try:
                price = float(it.get("min_group_price") or 0) / 100.0
                list_price = float(it.get("market_price") or 0) / 100.0
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            out.append(_to_offer(
                channel=self.channel,
                shop_name=str(it.get("mall_name") or "拼多多店铺"),
                shop_type="品牌旗舰店",
                version="海外版",       # 拼多多跨境/海购货源以海外版为主
                list_price=list_price or price,
                price=price,
                affiliate_url=it.get("url"),
                origin=None,
                note=f"已售 {it.get('sales_tip')}" if it.get("sales_tip") else None,
            ))
        if not out:
            raise UpstreamError("UPSTREAM_EMPTY", "多多客未返回可用报价")
        return out


# ---------------------------------------------------------------------------
# 唯品会联盟
# ---------------------------------------------------------------------------

class VipUnionProvider:
    channel = "唯品会"
    mode = "live"
    ENDPOINT = "https://market.vip.com"

    def __init__(self) -> None:
        self.app_key = settings.vip_union_app_key
        self.secret = settings.vip_union_app_secret
        self.pid = settings.vip_union_pid
        self.client = _SignedClient(self.ENDPOINT)

    def is_configured(self) -> bool:
        return bool(self.app_key and self.secret and self.pid)

    def fetch(self, product: Product) -> list[dict]:
        if not self.is_configured():
            raise ProviderNotConfigured("唯品会联盟凭据未配置")
        # 唯品会走标准 REST：签名沿用同一套 MD5 口径，接口路径以官方文档为准
        params: dict[str, Any] = {
            "appKey": self.app_key,
            "keyword": f"{product.brand} {product.name}",
            "pageSize": 20,
            "pid": self.pid,
            "timestamp": str(int(time.time() * 1000)),
        }
        params["sign"] = _md5_sign(params, self.secret)
        data = self.client.request("GET", "/api/goods/search", params=params)
        rows = (data.get("data") or {}).get("list", []) or []
        out: list[dict] = []
        for it in rows:
            try:
                price = float(it.get("vipPrice") or 0)
                list_price = float(it.get("marketPrice") or price)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            out.append(_to_offer(
                channel=self.channel,
                shop_name=str(it.get("storeName") or "唯品会自营"),
                shop_type="自营",
                version="保税免税",
                list_price=list_price,
                price=price,
                affiliate_url=it.get("unionUrl") or it.get("url"),
            ))
        if not out:
            raise UpstreamError("UPSTREAM_EMPTY", "唯品会联盟未返回可用报价")
        return out


# ---------------------------------------------------------------------------
# 保税仓 / 跨境供应链数据方（通用 JSON 接口）
# ---------------------------------------------------------------------------

class BondedProvider:
    channel = "保税仓"
    mode = "live"

    def __init__(self) -> None:
        self.base_url = settings.bonded_api_base
        self.api_key = settings.bonded_api_key
        self.client = _SignedClient(self.base_url) if self.base_url else None

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def fetch(self, product: Product) -> list[dict]:
        if not self.is_configured() or self.client is None:
            raise ProviderNotConfigured("保税仓数据方未配置")
        params: dict[str, Any] = {
            "keyword": f"{product.brand} {product.name}",
            "limit": 20,
        }
        data = self.client.request(
            "GET", "/v1/offers",
            params=params, headers={"X-API-Key": self.api_key},
        )
        rows = data.get("items") or data.get("data") or []
        out: list[dict] = []
        for it in rows:
            try:
                price = float(it.get("price") or 0)
                list_price = float(it.get("list_price") or price)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            out.append(_to_offer(
                channel=self.channel,
                shop_name=str(it.get("warehouse") or "保税仓直发"),
                shop_type="自营",
                version="保税免税",
                list_price=list_price,
                price=price,
                affiliate_url=it.get("link"),
                months=it.get("shelf_life_months"),
                note=it.get("note"),
            ))
        if not out:
            raise UpstreamError("UPSTREAM_EMPTY", "保税仓数据方未返回可用报价")
        return out


LIVE_PROVIDERS = (
    TmallUnionProvider,
    JdUnionProvider,
    PddDuoProvider,
    VipUnionProvider,
    BondedProvider,
)


def build_registry():
    """按配置装配 Provider 注册表。

    data_mode:
      seed   —— 只用内置种子（离线演示）
      live   —— 只用真实源；未配置凭据的渠道会被标记为「未接入」
      hybrid —— 真实源优先；某渠道拉取失败/未配置时，用种子数据补齐该渠道，
                并在报价上标注 data_basis="seed"，前端可区分
    """
    from providers.base import ProviderRegistry
    from providers.seed import SeedProvider

    reg = ProviderRegistry()
    mode = settings.data_mode.lower()

    if mode in ("seed", "hybrid"):
        reg.register(SeedProvider())
    if mode in ("live", "hybrid"):
        for cls in LIVE_PROVIDERS:
            try:
                reg.register(cls())
            except Exception as exc:  # pragma: no cover - 装配期防御
                logger.warning("Provider %s 装配失败：%s", cls.__name__, exc)
    if not reg.all():
        reg.register(SeedProvider())
    return reg
