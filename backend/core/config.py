"""集中配置（pydantic-settings）。

所有可变项一律走环境变量，代码内不留硬编码的域名、端口、凭据、路径。
未配置的外部依赖（联盟凭据 / 微信推送）不会导致启动失败，而是让对应能力
进入「未接入」状态并在 API 响应里如实标注 —— 见 settings.feature_* 属性。
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- 基础
    app_name: str = "采选美妆 AI"
    app_version: str = "3.0.0"
    env: str = "dev"                      # dev | staging | prod
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = False                # 生产建议 true（结构化日志）

    # ---------------------------------------------------------------- 服务
    host: str = "127.0.0.1"
    port: int = 8000
    # 允许跨域的来源白名单（逗号分隔）。生产必须显式收敛，禁止 "*"。
    cors_origins: str = "http://127.0.0.1:3000,http://localhost:3000"

    # ---------------------------------------------------------------- 存储
    # 留空 -> 使用 SQLite（开发默认）。生产填 postgresql+psycopg://user:pw@host/db
    database_url: str = ""
    sqlite_path: str = "data/caixuan.db"
    db_echo: bool = False

    # ---------------------------------------------------------------- 鉴权
    session_secret: str = ""              # 为空时自动生成运行时密钥（仅 dev 可接受）
    session_ttl_seconds: int = 60 * 60 * 24 * 30
    # 允许匿名设备会话（一期 H5 无强制登录；小程序/H5 登录后升级为绑定会话）
    allow_anonymous_session: bool = True

    # ---------------------------------------------------------------- 数据源
    # live = 只信真实凭据，未配置的渠道返回「未接入」；seed = 使用内置种子数据集
    data_mode: str = "seed"               # seed | live | hybrid
    price_cache_ttl_seconds: int = 300
    outbound_timeout_seconds: float = 8.0
    outbound_max_retries: int = 2
    # 数据源中文标注（对外展示「数据来源」用）
    data_source_label: str = "公开渠道行情聚合"

    # 各渠道联盟凭据（缺失即视为该渠道未接入）
    tmall_union_app_key: str = ""
    tmall_union_app_secret: str = ""
    tmall_union_pid: str = ""
    jd_union_app_key: str = ""
    jd_union_app_secret: str = ""
    jd_union_pid: str = ""
    pdd_duo_app_key: str = ""
    pdd_duo_app_secret: str = ""
    pdd_duo_pid: str = ""
    vip_union_app_key: str = ""
    vip_union_app_secret: str = ""
    vip_union_pid: str = ""
    bonded_api_base: str = ""
    bonded_api_key: str = ""

    # ---------------------------------------------------------------- 推送
    wechat_mp_app_id: str = ""
    wechat_mp_app_secret: str = ""
    wechat_mp_template_id: str = ""
    wechat_mini_app_id: str = ""
    wechat_mini_app_secret: str = ""
    wechat_mini_template_id: str = ""
    push_enabled: bool = False            # 只有凭据齐全时才应置 true
    push_interval_minutes: int = 30       # 定时比价轮询间隔
    #: 同一订阅的推送冷却（小时）—— 防止价格在阈值附近抖动导致反复打扰用户
    push_cooldown_hours: int = 12
    #: 微信模板字段映射（JSON）。留空使用内置默认映射 thing1/amount2/amount3/date4/thing5。
    #: 各账号模板字段编号不同，运营侧按自己申请的模板填此值即可，无需改代码。
    wechat_template_fields: str = ""
    #: 定时比价轮询开关（无 scheduler 依赖时自动跳过）
    poll_enabled: bool = True

    # ---------------------------------------------------------------- 合规
    # 免责声明唯一来源：全站（后端各路由 + 前端）都必须引用它，不得各处自行改写
    disclaimer: str = (
        "本平台仅聚合公开价格、货源及行情信息，不提供真伪鉴定服务，"
        "不承诺正品；商品正品性、售后维权由跳转电商平台全权负责。"
        "所有价格均为「行情参考价」，非锁定成交价，不构成交易要约。"
    )
    price_label: str = "行情参考价"
    # 临期阈值（月）：剩余保质期 ≤ 该值自动打「临期预警」
    near_expiry_months: int = 6

    # ---------------------------------------------------------------- 计算
    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.sqlite_path}"

    @property
    def is_sqlite(self) -> bool:
        return self.sqlalchemy_url.startswith("sqlite")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # ---------------------------------------------------------------- 能力开关
    @property
    def configured_channels(self) -> list[str]:
        """已配置凭据的渠道（其余渠道会以「未接入」呈现，不伪造数据）。"""
        out = []
        if self.tmall_union_app_key and self.tmall_union_pid:
            out.append("天猫")
        if self.jd_union_app_key and self.jd_union_pid:
            out.append("京东")
        if self.pdd_duo_app_key and self.pdd_duo_pid:
            out.append("拼多多")
        if self.vip_union_app_key and self.vip_union_pid:
            out.append("唯品会")
        if self.bonded_api_base:
            out.append("保税仓")
        return out

    @property
    def wechat_ready(self) -> bool:
        return bool(
            self.wechat_mp_app_id
            and self.wechat_mp_app_secret
            and self.wechat_mp_template_id
        )

    @property
    def wechat_mini_ready(self) -> bool:
        return bool(
            self.wechat_mini_app_id
            and self.wechat_mini_app_secret
            and self.wechat_mini_template_id
        )

    @property
    def push_ready(self) -> bool:
        return self.push_enabled and (self.wechat_ready or self.wechat_mini_ready)

    @property
    def template_fields(self) -> dict[str, str]:
        """微信模板字段映射。

        运营侧按自己申请的模板填入（JSON），默认给一套常见口径。
        映射缺失时退回默认，保证「凭据齐全即可推送」。
        """
        default = {
            "product": "thing1",
            "price": "amount2",
            "target": "amount3",
            "time": "date4",
            "channel": "thing5",
        }
        raw = (self.wechat_template_fields or "").strip()
        if not raw:
            return default
        import json

        try:
            parsed = json.loads(raw)
        except ValueError:
            return default
        if not isinstance(parsed, dict):
            return default
        return {k: str(v) for k, v in {**default, **parsed}.items()}

    @property
    def push_cooldown_seconds(self) -> int:
        return max(0, int(self.push_cooldown_hours)) * 3600

    @property
    def is_prod(self) -> bool:
        return self.env.lower() in ("prod", "production")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
