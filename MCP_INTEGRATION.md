# MCP_INTEGRATION —— 麦当劳 MCP Server 集成说明

本文档说明 mcd-smart-order skill 实际使用的 MCP Server、工具清单、调用流程与业务价值。

## 1. MCP Server 概览

| 项目 | 说明 |
|---|---|
| Server 名称 | mcd-mcp（麦当劳官方智能点餐连接器） |
| 接入方式 | WorkBuddy 连接器（MCP 协议），需在连接器管理中启用并登录麦当劳账号 |
| 认证 | OAuth 账号授权，登录后自动携带会员身份（积分、卡包券随账号生效） |
| 数据性质 | 全部为麦当劳官方实时接口数据：门店、在售菜单、价格、营养成分、优惠券、订单 |

skill 本身不持有任何业务数据，所有真实数据均通过 mcd-mcp 工具实时获取。

## 2. 实际使用的 Tool 清单

### 主流程必用

| Tool | 用途 | 关键输入 | 关键输出 |
|---|---|---|---|
| `query-nearby-stores` | 查附近门店（到店/得来速） | city, keyword, beType | storeCode, beCode(得来速) |
| `delivery-query-stores` | 查可外送门店 | 地址参数 | storeCode, beCode |
| `query-meals` | 门店在售菜单 | storeCode, orderType, beType | productCode, 价格, 随单购 |
| `list-nutrition-foods` | 常见餐品营养成分表（无参数，全量） | — | 能量kcal, 蛋白质, 脂肪, 碳水, 钠 |
| `query-store-coupons` | 指定门店实际可用的券 | storeCode, orderType, beType | 券ID/code, 优惠规则 |
| `calculate-price` | 含优惠实付价计算 | storeCode, items[] | 实付价(单位：**分**), takeWayList |
| `create-order` | 创建订单 | storeCode, items[], takeWayCode/addressId | 订单ID, 支付引导 |
| `query-order` | 查询订单状态 | 订单参数 | 订单状态 |

### 按需使用

| Tool | 用途 |
|---|---|
| `query-meal-detail` | 餐品详情与特制选项（modification 的 selectedKey/unselectedKey 规则） |
| `query-my-coupons` | 卡包全部券（不做门店校验，不承诺可用于当前订单） |
| `query-my-account` | 会员积分/账户 |
| `delivery-query-addresses` / `delivery-create-address` | 外送地址查/建 |
| `campaign-calendar` | 当月营销活动日历（1024 等节日活动信息来源） |
| `query-lottery-info` / `draw-lottery` | 积分抽奖查询/参与 |
| `mall-points-products` / `mall-product-detail` / `mall-create-order` | 积分商城兑换（多商品必须分别排队下单） |
| `cancel-order` / `order-list` | 取消订单 / 历史订单 |

## 3. 调用流程（点餐推荐主链路）

```
用户："30元内、600大卡，配一顿麦当劳，到店自取"
  │
  ├─ ① query-nearby-stores(beType=1, searchType=2)     → 用户选门店 → storeCode
  │
  ├─ ② query-meals(storeCode, orderType=1, beType=1)    → 菜单+价格+productCode
  │     list-nutrition-foods()                          → 全量营养表
  │     query-store-coupons(storeCode, …)               → 该店可用券
  │
  ├─ ③ AI 按名称将菜单 × 营养表关联
  │     匹配不到 → 标注"热量未知"，不入组合
  │     每类挑 2-3 个候选 → 写入 candidates.json
  │
  ├─ ④ python scripts/combo_optimizer.py candidates.json
  │     → 枚举「主餐+小食+饮品」组合
  │     → 过滤：实付价≤预算 且 总热量≤上限
  │     → 按 prefer 排序输出 Top N（JSON）
  │
  ├─ ⑤ AI 套用优惠券 + calculate-price(items[]) 验证实付价
  │     超预算 → 回 ③ 调整
  │
  ├─ ⑥ 展示 2-3 套方案（搭配/总价/总热量/余量）→ 用户选定并确认
  │
  └─ ⑦ create-order(storeCode, items[], takeWayCode)
        → 引导支付 → 用户回复"支付完成/失败" → query-order 确认
```

### 参数配对规则（易错点）

| 场景 | beType | orderType | beCode | takeWayCode | addressId |
|---|---|---|---|---|---|
| 到店自取 | 1 | 1 | 不传 | 必传 | — |
| 得来速 | 5 | 1 | 必传 | 必传 | — |
| 麦乐送外送 | 2 | 2 | 必传 | — | 必传 |

- `takeWayCode` 必须来自 `calculate-price` 返回的 `takeWayList[].code`
- `calculate-price` 与 `create-order` 的金额单位均为**分**，展示时除以 100
- 门店编码 storeCode 必须全数字

### 失败处理

| 情况 | 处理 |
|---|---|
| 组合搜索无可行解（脚本退出码 3） | 向用户说明约束过紧，建议放宽预算/热量或去掉小食 |
| 脚本输入错误（退出码 2） | 检查 candidates.json 格式后重试 |
| 营养表缺某商品 | 如实标注"热量未知"，禁止编造；该商品不参与约束计算 |
| 优惠券在门店不可用 | 以下单前 `query-store-coupons` / `calculate-price` 结果为准 |

## 4. 业务价值

**对用户：**

1. **把"能不能吃"变成精确计算**：以往靠感觉估热量，现在每套方案都给出基于官方营养表的总热量，减脂人群可以放心吃麦当劳
2. **把预算用满不超支**：券与实时价格参与计算，推荐的是"当前门店、当前账号"真实可成交的价格，而非菜单标价
3. **一句话替代多步操作**：传统流程 = 打开APP → 选门店 → 翻菜单 → 心算热量比价 → 加购 → 核价 → 下单，共 7 步；现在 1 句话 + 1 次确认
4. **确定性推荐**：组合枚举由脚本完成，同样输入必然得到同样结果，避免大模型"口算"出错

**对开发者/参赛角度：**

1. **典型的 MCP + Skill + Script 三层架构**：MCP 提供实时业务数据与交易能力，Skill 沉淀领域工作流与规则，Script 保证核心计算确定性——可复用的集成范式
2. **交易闭环**：不止推荐，还能验价、下单、跟单，跑通了 MCP 从"读"到"写"的完整链路
3. **可扩展**：`combo_optimizer.py` 的输入是通用 JSON（价格+热量+类别），换一套数据源即可适配其他餐饮品牌

## 5. 安全与边界

- 所有下单类工具（create-order / mall-create-order / draw-lottery）必须经用户明确确认后才调用
- 不缓存、不落盘用户的账号与订单敏感信息；candidates.json 仅为临时文件
- 营养数据为静态参考，特制选项（去酱/加料）引起的热量变化不参与计算，已在推荐话术中向用户说明
