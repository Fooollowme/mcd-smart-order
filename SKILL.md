---
name: mcd-smart-order
description: 麦当劳智能点餐推荐 skill。根据用户设定的消费预算（如"30 元以内"）和热量目标（如"这顿不超过 800 大卡"），结合麦当劳门店菜单价格与营养成分数据，推荐满足双约束的搭配方案，并可直接下单。当用户提到"麦当劳点餐"、"帮我搭配一顿麦当劳"、"预算内吃麦当劳"、"控制热量点麦当劳"、"瘦身也能吃麦当劳"等场景时使用。依赖 mcd-mcp 连接器（已登录麦当劳账号）。
agent_created: true
---

# Mcd Smart Order

按「消费预算 + 热量目标」双约束推荐麦当劳搭配，并支持直接下单。

## 核心工作流（5 步）

### Step 1: 收集约束

向下确认四个要素，缺失时逐项追问（一次问全，不要挤牙膏）：

1. **预算上限**：这顿最多花多少钱（如 30 元）
2. **热量目标**：这顿不超过多少大卡（如 800 kcal）；用户没概念时给出参考：减脂单餐建议 500-700 kcal，普通单餐 800-1000 kcal
3. **用餐地点/方式**：到店自取（beType=1）、得来速（beType=5）还是麦乐送外送（beType=2）
4. **口味偏好**：有无忌口、必点项、不吃的东西（如不吃辣、不要生洋葱）

### Step 2: 定位门店

- 到店/得来速：调用 `query-nearby-stores`（searchType=2 按位置搜，需 city+keyword）。引导用户选门店，拿到 storeCode（得来速还拿 beCode）
- 外送：调用 `delivery-query-stores` 查可配送门店，调用 `delivery-query-addresses` / `delivery-create-address` 拿地址。外送需额外预留配送费，从预算中先扣减

### Step 3: 数据拉取与关联（推荐的核心）

1. 调用 `query-meals` 获取该门店当前在售菜单（价格、productCode、随单购）
2. 调用 `list-nutrition-foods` 获取餐品营养数据（能量 kcal、蛋白质、脂肪、碳水、钠）
3. **名称关联**：把菜单项与营养表按名称匹配（如"麦辣鸡腿堡"对应营养表同名项）。匹配不上的项（限定款、新品）如实标注"热量未知"，不要编造数字
4. 优惠券：调用 `query-my-coupons` 看卡包券；若已定门店，调用 `query-store-coupons` 看该门店实际可用的券。券能降低实付价，优先在预算内用上

### Step 4: 生成推荐方案

对「主餐 + 小食 + 饮品」结构做组合搜索，满足：**实付价 ≤ 预算** 且 **总热量 ≤ 热量目标**。实操规则：

- **组合空间**：主餐取 2-3 个候选汉堡/卷，小食 2-3 个，饮品 2-3 个，枚举组合即可，无需复杂算法
- **省热量的默认技巧**：饮品优先零卡（零度可乐、无糖茶）；酱料减半或去掉；薯条选小份；优先烤/板烧类而非炸类
- **省钱技巧**：优先用券组合（如 5 折三件套券直接当一套方案）；留意随单购优惠；套餐通常比单点便宜
- **组合搜索用脚本完成**：将已关联好热量和价格的候选商品（主餐/小食/饮品各 2-3 个）写入 JSON 临时文件，调用 `scripts/combo_optimizer.py` 枚举组合并排序：
  ```bash
  python scripts/combo_optimizer.py candidates.json --top 3 --prefer balanced
  ```
  `--top`（方案数）和 `--prefer`（balanced/low_cal/protein/value）可省略，省略时取 JSON 内的 top/prefer 字段或默认值。完整链路：MCP 拿菜单和营养数据 → AI 按名称关联热量并格式化为 JSON → 写临时文件 → 执行脚本 → 解析 JSON 输出 → 套用优惠券并整理成推荐话术
- 脚本约定：输出为 JSON（combos + warnings）；退出码 2=输入错误、3=无可行组合。候选商品缺热量的会被自动跳过并写入 warnings，须向用户如实说明
- **输出 2-3 套方案**，每套展示：搭配清单、预估总价、总热量、所用券。按不同侧重排序：如「最省热量」「性价比最高」「最饱腹（蛋白质最高）」
- 热量只做**静态估算**（基于营养表），最终价格必须用 `calculate-price` 校验（返回单位为**分**，展示时除以 100）

### Step 5: 确认与下单

1. 用户选定方案后，调用 `calculate-price` 得到含优惠实付价。若超预算，回到 Step 4 调整并说明原因
2. 用户确认价格后，调用 `create-order` 下单：
   - 到店自取（beType=1, orderType=1）：需传 takeWayCode（来自 calculate-price 返回的 takeWayList[].code）
   - 得来速（beType=5, orderType=1）：需传 beCode + takeWayCode
   - 外送（beType=2, orderType=2）：需传 addressId，可引导填备注和 needTableware
   - 套餐特制项：modification 的 key 规则严格遵循 `query-meal-detail` 返回的 selectedKey/unselectedKey（组内所有特调项都必须传）
3. 下单后引导用户支付，收到"支付完成/失败"回复后用 `query-order` 查最新状态

## 硬性规则

- **禁止未确认下单**：必须经 calculate-price 展示实付价、用户明确确认后才调用 create-order
- **禁止编造热量**：营养表匹配不到的餐品标注"热量未知"，不得估计后冒充真实数据
- **预算包含外送费**：外送场景先确认配送费再谈搭配
- **工具间参数配对**：beType/beCode/orderType/storeCode 的配对关系出错是最高频报错源，每次调用前核对
- 门店编码 storeCode 必须全数字

## 参考文件

- `references/mcd-tool-map.md` — mcd-mcp 全量工具清单、参数配对表与常见坑。遇到报错或不确定参数时先读它
