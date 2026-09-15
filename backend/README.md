# 采选美妆 AI · 后端服务（v3.0）

> **国际大牌护肤美妆 · AI 对话选型 + 多平台比价 + 货源风险筛查** Web/H5 平台后端。
> 技术栈：FastAPI + SQLAlchemy 2.0 + Pydantic v2；数据源走 **Provider 注册表**，凭据齐全即自动切真流量。

## 快速开始

```bash
# 1) 建虚拟环境并装依赖（Python ≥ 3.11）
python -m venv .venv
# Windows: .venv\Scripts\activate   ｜ macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 2) 配置（不改也能跑，默认 seed 演示数据集 + SQLite）
cp .env.example .env

# 3) 启动
uvicorn main:app --host 0.0.0.0 --port 8000
```

健康检查 <http://127.0.0.1:8000/healthz> ｜ 接口文档 <http://127.0.0.1:8000/docs> ｜ 就绪探针 `/readyz`

> `DATA_MODE` 三档：`seed`（默认，内置演示数据集，全站如实标注「演示数据」）/
> `hybrid`（真实渠道优先，未接入渠道用演示数据补齐）/ `live`（**纯真实**，缺源即报错，不做静默兜底）。

## 模块 ↔ 接口（M1–M5）

| 模块 | 接口 | 说明 |
|---|---|---|
| M1 AI 对话选型 | `POST /api/dialogue/chat` | 自然语言 → 结构化意图 + 固定五段回复【适配推荐｜全网比价｜版本差异｜入手建议｜风险提示】 |
| M2 全网比价看板 | `GET /api/compare/result?q=` | 5 渠道 × 到手价/版本/风险/优惠 四维 + 版本差异对比 |
| M3 价格行情 | `GET /api/trend/series?q=` | 90 天走势 + 30/90 天最低 + 档位判定 + 形态识别 + 入手建议 |
| M4 降价订阅 | `GET/POST /api/alert/*` | 心理底价订阅 + 真实触发判定 + 微信推送（未配置时如实报 `not_configured`） |
| M5 一键跳转 | `POST /api/offer/click` + `offers[].cps_url` | CPS 溯源链接 + 点击上报；后端不承接履约与售后 |
| 会话 | `POST /api/auth/session` | 设备/匿名会话签发，越权读写拦截 |
| 可观测 | `GET /healthz` `/readyz` `/api/meta/sources` | 存活/就绪/数据源真实状态 |

## 目录结构

```
backend/
├── main.py                 # 入口：中间件 + CORS 白名单 + 路由注册 + 启动迁移/调度
├── core/
│   ├── config.py           # 配置层（.env / 环境变量，含合规文案单一来源）
│   ├── domain.py           # 领域规则：渠道/版本/风险标签、价格分（整数分）、排序、形态识别
│   ├── catalog.py          # 商品主数据 + 查询词归一 + SKU 对齐
│   ├── db.py               # SQLAlchemy 引擎/会话 + 幂等迁移
│   ├── models.py           # ORM：会话、订阅、推送日志、点击数、价格快照
│   ├── security.py         # 会话签发/解析/归属校验
│   ├── errors.py           # 领域异常 + 统一错误处理
│   └── observability.py    # 结构化日志 + X-Request-Id 链路
├── providers/
│   ├── base.py             # Provider 协议 + TTL 缓存 + 注册表
│   ├── seed.py             # 内置演示数据集（6 款 × 5 渠道）
│   ├── cps.py              # CPS 链接与 sub_id 构建（永不产出空链接）
│   └── live.py             # 真实渠道实现（凭据缺失即拒，不伪造）
├── services/
│   ├── market.py           # 比价聚合：对齐 → 取数 → 归一 → 排序 → 溯源
│   ├── dialogue.py         # M1 意图解析 + 五段式回复
│   ├── trend.py            # M3 行情：真实快照优先，不足则回退演示序列
│   ├── versions.py         # M2 版本差异对比
│   ├── alert.py            # M4 订阅评估与触发判定
│   ├── push.py             # M4 微信推送发送器（如实上报状态）
│   └── scheduler.py        # 定时比价轮询
├── routers/                # auth / dialogue / compare / trend / alert / offer / meta
├── scripts/smoke.py        # 端到端冒烟（真实 HTTP，CI 可用）
└── tests/                  # pytest 155 项
```

## 接入真实数据源

三类 Provider 已就位，**只差凭据**：在 `.env` 填好对应渠道凭据，并把 `DATA_MODE` 切到 `hybrid` 或 `live` 即自动生效，前端契约零改动。

- **CPS/价格源**：淘宝联盟（天猫） / 京东联盟 / 拼多多推手 / 唯品会联盟 / 保税仓数据方
- **策略**：官方与授权接口优先 → 联盟 API → 第三方聚合 → 爬虫仅兜底（不缓存、不转售原始商品库）
- **凭据缺失时的行为**：`live` 模式直接报 `PROVIDER_NOT_CONFIGURED`，**绝不静默返回假数据**
- **溯源**：每次取数写入 `sources` 标注，`data_basis` 如实反映本轮是 `live` / `seed` / `mixed`

## 全站唯一口径（改动需同步前端 `lib/api.ts`）

| 项 | 取值 |
|---|---|
| 渠道（5） | 天猫、京东、拼多多、唯品会、保税仓 |
| 核心对比渠道（4） | 天猫自营、京东自营、保税仓、拼多多品牌店 |
| 版本（3 类） | 国行 / 保税免税 / 海外版（日版、韩免、欧版为海外版下产地细分） |
| 风险标签（4） | 临期预警、无专柜联保、捆绑消费溢价、第三方店铺售后风险 |
| 临期阈值 | 剩余保质期 ≤ 6 个月自动打 `临期预警` |
| 金额单位 | 一律 **整数分**（`price_cents`），避免浮点相等比较出错 |
| 到手价 | = 标价 −（券 + 立减 + 补贴），与优惠明细强自洽（`price_consistent`） |

> `RISK_TAGS` 与 `VERSIONS` 是白名单，`normalize_offer()` 会过滤白名单外的标签，防脏数据绕过合规口径。

## 合规红线（不可绕过）

1. **不提供真伪鉴定服务、不承诺正品**；只做版本差异科普、临期风险筛查、渠道优劣提示。
2. 所有价格必须表述为「**行情参考价**」，非锁定成交价；前端固定免责条不得删除。
3. 不得出现「真 / 疑 / 假」等鉴定性结论或「正品保障 / 假货 / 鉴定为真」措辞。
4. `sponsored` 位必须透明标注，且**不参与默认排序**；「最低到手价」徽章只授予非赞助位。
5. 严禁把未实际对接的第三方机构写入文案做背书。

## 测试

```bash
pytest -q                       # 155 项单元/接口测试
python scripts/smoke.py --base http://127.0.0.1:8000   # 真实 HTTP 端到端冒烟
```

## 依赖

见 `requirements.txt`（FastAPI / uvicorn / SQLAlchemy / pydantic-settings / APScheduler / httpx / pytest）。
