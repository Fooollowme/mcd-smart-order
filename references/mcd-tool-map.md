# mcd-mcp 工具地图与常见坑

mcd-mcp 连接器全量工具清单。按用途分组，标注关键参数与坑点。

## 参数配对总表（最高频报错源）

| 场景 | beType | orderType | beCode | 门店查询工具 |
|---|---|---|---|---|
| 到店自取 | 1 | 1 | 不传 | query-nearby-stores |
| 得来速(DT) | 5 | 1 | 必传（来自 query-nearby-stores） | query-nearby-stores |
| 麦乐送外送 | 2 | 2 | 必传（来自 delivery-query-stores） | delivery-query-stores |
| 企业团餐 | 6 | 2 | 必传（来自 delivery-query-stores） | delivery-query-stores |

- storeCode 全部由数字组成
- 到店自取场景传 beCode 会报错，切记不传
- 预约场景才传 reservationDate，格式 `yyyy-MM-dd HH:mm`

## 工具清单

### 门店与地址
- `query-nearby-stores`：到店/得来速查门店。searchType=2 按位置（需 city+keyword），searchType=1 查收藏
- `delivery-query-stores`：外送查门店
- `delivery-query-addresses` / `delivery-create-address`：外送地址查/建

### 菜单与营养
- `query-meals`：门店在售菜单（价格、productCode、随单购商品）
- `query-meal-detail`：餐品详情与特调（modification）。selectedKey/unselectedKey 规则：含 unselectedKey 的特调组内**所有项都必须传入**，选中的用 selectedKey，未选中的用 unselectedKey
- `list-nutrition-foods`：常见餐品营养数据（能量/蛋白/脂肪/碳水/钠）。无参数，一次拉全量。与菜单按名称关联，匹配不上就标"热量未知"

### 价格与优惠券
- `calculate-price`：含优惠实付价。**返回价格单位为"分"**，展示需除以 100。返回 takeWayList[].code（下单必用）
- `query-my-coupons`：卡包全部券（不做门店/渠道校验，不承诺可用于当前订单）
- `query-store-coupons`：指定门店+订单类型下实际可用的券
- `available-coupons` / `auto-bind-coupons`：可领券与自动领券

### 下单与订单
- `create-order`：创建订单。到店/得来速需 takeWayCode；外送需 addressId
- `query-order` / `order-list` / `cancel-order`：订单查/列/取消
- `query-promotions`：**仅企业团餐**场景的满减/满折规则

### 活动与积分
- `campaign-calendar`：当月营销活动日历
- `query-lottery-info` / `draw-lottery`：积分抽奖查询/抽奖。抽奖前**必须**展示 drawDecision.nextConsumption 并获用户明确确认，能否抽以 resourceEligible 为准
- `query-my-prizes`：抽奖奖品记录
- `mall-points-products` / `mall-product-detail` / `mall-create-order`：积分商城兑换。仅 shopId=2；**多个商品必须分别下单且排队**（前一单成功后再下下一单）；虚拟券 spuCategory=1，实物 spuCategory=2（需 addressId）
- `query-my-account`：会员账户/积分
- `party-order-create` 及 `query-party-*`：生日派对/亲子活动预订
- `query-survey-coupon`：问卷券
- `now-time-info`：当前时间

## 常见坑速查

1. **到店自取传了 beCode 报错** — 到店自取不传 beCode
2. **价格显示 1590** — 单位是分，除以 100 展示为 15.9 元
3. **下单缺 takeWayCode** — 先 calculate-price，从返回取
4. **热量对不上菜单** — 营养表是静态全量数据，限定款/新品可能缺失，如实标注
5. **券"有但不能用"** — query-my-coupons 不做校验，下单前用 query-store-coupons 确认
6. **抽奖自动连抽** — 严禁；每次抽都要展示消耗并确认
