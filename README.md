# 采选美妆 AI · 国际大牌护肤美妆 AI 比价平台

> 站在买货这一边的 AI 参谋：一句话说清预算 / 肤质 / 诉求 → 跨 **天猫 · 京东 · 拼多多 · 唯品会 · 保税仓**
> 五渠道比价，叠加**版本差异科普 · 临期风险筛查 · 渠道优劣提示**。
>
> 不提供真伪鉴定服务、不承诺正品；所有价格为「行情参考价」，非锁定成交价。

当前版本 **v3.0**（一期，Web/H5 优先；小程序二期复用同一套 REST）。

---

## 一、它解决什么问题

| 用户的真实痛点 | 平台给出的答案 | 落地模块 |
|---|---|---|
| 同一款精华 5 个平台价格差 30%，但算不清「券 + 满减 + 赠品」后的真实到手价 | 优惠四要素拆解，还原到手价并逐项可复核 | M2 |
| 不知道自己该买哪款、哪一档 | 按肤质 / 诉求 / 预算做适配推荐，给候选清单而不是硬塞一款 | M1 |
| 国行 / 保税免税 / 海外版到底差在哪 | 三类版本的成分、保质期标注、国内联保差异科普 | M2 |
| 低价背后可能是临期、无联保、捆绑、第三方售后 | 四个风险标签自动筛查，逐条给出命中渠道 | M2 |
| 不知道现在该不该买 | 区间行情 + 档位判定 + 走势形态识别，给「入手 / 观望 / 囤货」建议 | M3 |
| 想等降价但没空盯 | 订阅心理底价，命中即提醒（真实推送，非假装） | M4 |
| 看完想买但找不到入口 | 一键跳转真实渠道页面，带溯源归因 | M5 |

---

## 二、目录结构

```
caixuan-web/
├── backend/                      FastAPI 后端
│   ├── core/                     口径与基座（全项目唯一真相来源）
│   │   ├── config.py             集中配置（全部走环境变量，无硬编码）
│   │   ├── domain.py             ★ 渠道/版本/风险标签枚举、到手价推导、档位与形态算法
│   │   ├── catalog.py            ★ 商品主数据与 SKU 对齐（绝不回落默认商品）
│   │   ├── db.py                 引擎/会话/幂等迁移（SQLite ↔ Postgres 同一套代码）
│   │   ├── models.py             ORM：会话·订阅·推送日志·点击·价格快照
│   │   ├── security.py           会话鉴权与归属校验
│   │   ├── errors.py             统一错误体（前端只需处理一种形状）
│   │   └── observability.py      请求链路 ID + 结构化日志
│   ├── providers/                数据源（统一 PriceProvider 协议）
│   │   ├── base.py               协议 + TTL 缓存 + 注册表
│   │   ├── live.py               淘宝联盟/京东联盟/多多客/唯品会/保税仓 真实接口
│   │   ├── seed.py               内置演示数据集（离线可用，逐条标注来源）
│   │   └── cps.py                ★ M5 跳转链接构建（永不产出空链接）
│   ├── services/                 业务编排
│   │   ├── market.py             比价聚合主链路
│   │   ├── trend.py              行情序列与快照落库
│   │   ├── versions.py           版本差异对比
│   │   ├── dialogue.py           ★ M1 意图解析 + 五段式结论生成
│   │   ├── alert.py              M4 订阅评估与推送编排
│   │   ├── push.py               ★ 微信公众号 / 小程序真实推送（含 token 缓存与错误码处理）
│   │   └── scheduler.py          价格轮询定时任务
│   ├── routers/                  HTTP 契约
│   │   ├── auth.py  dialogue.py  compare.py  trend.py  alert.py  offer.py
│   ├── tests/                    pytest（155 项）
│   ├── scripts/smoke.py          端到端冒烟（真实 HTTP，CI 可用）
│   ├── main.py                   应用入口（CORS 白名单 / 中间件 / 迁移 / 定时任务）
│   ├── requirements.txt
│   └── .env.example              ★ 全部可配置项与说明
│
├── frontend/                     Next.js 14 (App Router)
│   ├── app/                      页面：对话 / 比价 / 行情 / 订阅 / 我的
│   ├── components/
│   │   ├── Icons.tsx             ★ 全站内联 SVG 图标（零 emoji、零依赖）
│   │   ├── AppShell.tsx          外壳 + 全站免责条 + 后端连接状态
│   │   └── Cards.tsx             比价行 / 版本卡 / 建议卡 / 未连接占位
│   ├── lib/
│   │   ├── api.ts                ★ 类型化 API 客户端（不提供伪造兜底数据）
│   │   └── session.ts            设备会话与查询上下文
│   └── scripts/check-no-emoji.mjs  CI 守卫：禁止 UI 代码出现 emoji
│
├── docker-compose.yml            Postgres + 后端 + 前端 一键起
└── .github/workflows/ci.yml      测试 · 冒烟 · 类型检查 · 构建 · emoji 守卫
```

---

## 三、快速开始

### 方式 A：本地开发（两个终端）

```bash
# ---- 后端 ----
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # 默认 DATA_MODE=seed，开箱即可跑
uvicorn main:app --reload --port 8000
# 文档 http://127.0.0.1:8000/docs

# ---- 前端 ----
cd frontend
npm install
cp .env.example .env.local         # NEXT_PUBLIC_API_BASE 指向后端
npm run dev
# 页面 http://127.0.0.1:3000
```

### 方式 B：Docker 一键起（Postgres + 前后端）

```bash
cp backend/.env.example backend/.env
docker compose up -d --build
# 前端 http://localhost:3000   后端 http://localhost:8000/docs
```

> `NEXT_PUBLIC_API_BASE` 是**构建期**内联到浏览器产物的，
> 容器部署时必须填「浏览器能访问到的」地址（`http://localhost:8000` 或线上 API 域名），
> 不能填容器内网名 `backend:8000`。

### 验证安装

```bash
cd backend
pytest -q                                        # 单元 + 接口契约
python scripts/smoke.py --base http://127.0.0.1:8000   # 端到端（需服务已启动）

cd ../frontend
npm run verify                                   # 类型检查 + emoji 守卫 + 构建
```

---

## 四、默认状态说明（重要）

首次启动 **没有任何凭据** 也能跑通全部功能，此时：

| 能力 | 默认状态 | 表现 |
|---|---|---|
| 商品比价 / 行情 / 对话 | ✅ 可用 | 使用内置**演示数据集**，页面明确标注「演示数据集」 |
| 真实渠道行情 | ⛔ 未接入 | 5 个渠道标记为「未接入」，不伪造实时性 |
| 降价订阅 | ✅ 可用 | 监测真实生效（服务端定时轮询） |
| 微信推送 | ⛔ 未接入 | 如实显示「微信推送通道尚未接入」，**不会**假称已推送 |
| 微信登录 | ⛔ 未接入 | `/api/auth/wechat` 返回 501 并说明所需配置；匿名设备会话可用 |
| 会员支付 | ⛔ 未接入 | 按钮置灰，功能全部免费使用 |

接入清单见 `backend/.env.example`。填齐某一渠道的联盟凭据后，把 `DATA_MODE` 改为
`hybrid`（真实优先、缺失渠道用演示数据补齐并逐条标注）或 `live`（只用真实数据）。

---

## 五、工程上的三条硬约束

这一版的实现严格守三条线，它们是产品可信度的地基，不是可选项：

### 1. 数据来源必须可区分

每个响应都带 `data_basis`：`live`（真实渠道） / `seed`（演示数据集） / `mixed`（混合） / `snapshot`（历史快照）。
前端必须如实标注。**后端不可用时，前端不显示任何价格数字**，只显示「服务未连接 + 重试」——
对一个比价产品来说，展示写死的假价格比展示加载失败更糟。

### 2. 未接入的能力必须明说

不假装有数据、不假装已推送、不假装已登录、不假装有会员。
每个「未接入」的能力都有对应的用户可见文案（`push_status()["user_message"]` 等）。

### 3. 排序中立可验证

- 排序键是 `(是否赞助, 到手价)`：**赞助位不参与默认排序、永不置顶**
- 「最低到手价」徽章由后端 `cheapest()` 判定，只授予**非赞助位**，前端不得自行比较浮点
- 赞助位的**真实价格照常展示**（价格是客观事实），并通过 `absolute_lowest` 单独披露
- 付费推广位强制标注「赞助/佣金」，跳转链接带 `rel="sponsored"`

---

## 六、合规红线（不可突破）

1. **不提供真伪鉴定服务、不承诺正品**；商品正品性与售后维权由跳转电商平台全权负责
2. 所有价格均为「行情参考价」，非锁定成交价，**不构成交易要约**
3. 只做**版本差异科普 · 临期风险筛查 · 渠道优劣提示**，不做优劣背书
4. 不做「验真 / 鉴定 / 正品保障 / 真假对比 / 批号验真」类功能——这是产品定位的边界，不是暂未实现
5. 临期判定口径：剩余保质期 ≤ **6 个月**（`NEAR_EXPIRY_MONTHS`，全站唯一来源）

---

## 七、数据源参考

| 渠道 | 接入方式 | 需要的凭据 |
|---|---|---|
| 天猫 | 淘宝联盟 TOP（`taobao.tbk.dg.material.optional`） | `TMALL_UNION_APP_KEY/SECRET/PID` |
| 京东 | 京东联盟（`jd.union.open.goods.query`） | `JD_UNION_APP_KEY/SECRET/PID` |
| 拼多多 | 多多客（`pdd.ddk.goods.search`） | `PDD_DUO_APP_KEY/SECRET/PID` |
| 唯品会 | 唯品会联盟 | `VIP_UNION_APP_KEY/SECRET/PID` |
| 保税仓 | 跨境供应链数据方通用 JSON 接口 | `BONDED_API_BASE/KEY` |

> `providers/live.py` 已按各平台公开文档实现签名、参数拼装与响应映射，
> 但**尚未经线上联调验证**（当前环境无真实凭据）。凭据到位后需逐渠道跑一次真实请求核对字段。
> 未经联调的部分不会对外声称「已接入」——`/api/compare/sources` 就是这条线的对外口径。

推送通道同理：公众号模板消息 / 小程序订阅消息的实现在 `services/push.py`，
含 access_token 缓存与刷新、失效重试、错误码翻译，凭据缺失时如实回报 `not_configured`。

---

## 八、扩商品 / 扩渠道

- **新增商品**：在 `backend/core/catalog.py` 的 `CATALOG` 加一条（含别名与肤质/诉求标签），
  再到 `backend/providers/seed.py` 的 `SEED_OFFERS` 补 5 条渠道报价。
  **不要写 `price` 字段** —— 到手价由优惠拆解推导，测试会拦住手填常量。
- **新增渠道**：实现 `providers/base.py` 的 `PriceProvider` 协议 → 注册进 `build_registry()`
  → 在 `core/domain.py` 的 `CHANNELS` 加枚举 → 在 `providers/cps.py` 补跳转深链模板
  → 同步 `frontend/lib/api.ts` 的 `ChannelName`。

---

## 九、部署注意事项

- **生产必须显式配置 `CORS_ORIGINS`**（禁止 `*`）。`ENV=prod` 时若仍是通配符，服务会**拒绝启动**。
- `ENV=prod` 会自动关闭 `/docs`。
- 价格轮询调度器是**进程内**的：`POLL_ENABLED=true` 的实例必须只有一个，
  否则会重复推送。需要横向扩容时把轮询拆成独立进程。
- 微信同一 appid 的 access_token 全局唯一。当前用进程内缓存（单实例够用）；
  **多实例部署必须换成 Redis 集中缓存**，否则实例会互相顶掉 token。
- 探针：`/healthz`（存活，不查库）、`/readyz`（就绪，查库 + 数据源装配）。
- 数据库迁移是幂等的：启动时自动建表并应用增量 DDL，可重复执行。

---

## 十、版本

| 版本 | 范围 |
|---|---|
| v3.0（当前） | 一期：M1~M5 全部实现，可上线 |
| 二期 | 小程序端、B 端供应商撮合工作台、微信登录与会员支付 |
