#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦当劳「预算 + 热量」双约束套餐组合优化器。

从菜单（价格）+ 营养表（热量）人工关联出的商品清单中，
枚举「主餐 + 小食 + 饮品」组合，筛选满足预算与热量上限的方案并排序输出。

用法（stdlib only，无第三方依赖）：

    python combo_optimizer.py input.json [--top 3] [--prefer low_cal]
    cat input.json | python combo_optimizer.py

--top/--prefer 为可选命令行覆盖参数（覆盖 JSON 内同名字段）。

输入 JSON 格式：

    {
      "budget": 30.0,            # 必填，预算上限（元）
      "max_kcal": 700,           # 必填，热量上限（kcal）
      "top": 3,                  # 可选，输出方案数，默认 3
      "prefer": "balanced",      # 可选: balanced | low_cal | protein | value
      "items": [
        {"name": "麦辣鸡腿堡", "price": 25.5, "kcal": 549,
         "category": "main", "protein": 27.0},
        {"name": "小薯条", "price": 11.0, "kcal": 232, "category": "snack"},
        {"name": "零度可乐", "price": 9.5, "kcal": 0, "category": "drink"}
      ]
    }

category 取值：main(主餐) / snack(小食) / drink(饮品)，其他值归为 other（不参与组合）。
kcal 缺失的商品会被跳过并在 warnings 中提示（禁止编造热量）。

输出：JSON，含 combos[]（每套含明细、总价、总热量、预算/热量余量）与 warnings[]。

退出码：0 正常；2 输入错误；3 无可行组合。
"""

import argparse
import json
import sys

VALID_CATEGORIES = {"main", "snack", "drink"}


def load_input(args):
    """读取输入 JSON（文件或 stdin），解析失败时输出 JSON 错误并以退出码 2 结束。"""
    try:
        if args.input:
            with open(args.input, "r", encoding="utf-8") as f:
                return json.load(f)
        if sys.stdin.isatty():
            print(__doc__)
            sys.exit(2)
        return json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"输入不是合法 JSON：{e}"}, ensure_ascii=False))
        sys.exit(2)
    except OSError as e:
        print(json.dumps({"error": f"无法读取输入文件：{e}"}, ensure_ascii=False))
        sys.exit(2)


def parse_args():
    p = argparse.ArgumentParser(
        description="麦当劳「预算 + 热量」双约束套餐组合优化器",
        epilog="参数优先级：命令行 --top/--prefer 覆盖 JSON 内的同名字段")
    p.add_argument("input", nargs="?",
                   help="输入 JSON 文件路径；省略时从 stdin 读取")
    p.add_argument("--top", type=int, choices=range(1, 11),
                   help="输出方案数（1-10），覆盖 JSON 的 top 字段")
    p.add_argument("--prefer",
                   choices=["balanced", "low_cal", "protein", "value"],
                   help="排序偏好，覆盖 JSON 的 prefer 字段")
    return p.parse_args()


def normalize_items(raw_items, warnings):
    """校验并归一化商品；kcal/price 缺失或非法的丢弃并告警。"""
    items = {}
    for it in raw_items:
        name = str(it.get("name", "")).strip()
        if not name:
            continue
        try:
            price = float(it.get("price"))
            kcal = float(it.get("kcal"))
        except (TypeError, ValueError):
            warnings.append(f"跳过「{name}」：价格或热量缺失/非法（禁止编造数据）")
            continue
        cat = str(it.get("category", "other")).strip().lower()
        if cat not in VALID_CATEGORIES:
            cat = "other"
        protein = it.get("protein")
        try:
            protein = float(protein) if protein is not None else 0.0
        except (TypeError, ValueError):
            protein = 0.0
        # 同名商品保留更便宜的一份
        if name in items and items[name]["price"] <= price:
            continue
        items[name] = {
            "name": name, "price": price, "kcal": kcal,
            "category": cat, "protein": protein,
        }
    return items


def build_pool(items):
    pools = {c: sorted([v for v in items.values() if v["category"] == c],
                       key=lambda x: x["price"])
             for c in ("main", "snack", "drink")}
    # 每类只保留价格较低的前 6 个，控制枚举规模
    return {c: pool[:6] for c, pool in pools.items()}


def score_combo(combo, budget, max_kcal, prefer):
    price = sum(x["price"] for x in combo)
    kcal = sum(x["kcal"] for x in combo)
    protein = sum(x["protein"] for x in combo)
    budget_left = budget - price
    kcal_left = max_kcal - kcal
    if prefer == "low_cal":
        key = (kcal, -protein, price)
    elif prefer == "protein":
        key = (-protein, kcal, price)
    elif prefer == "value":
        key = (price, kcal, -protein)
    else:  # balanced：余量越均匀越好
        key = (abs(budget_left * 0.6) + abs(kcal_left * 0.02), price, kcal)
    return key, price, kcal, protein


def main():
    args = parse_args()
    data = load_input(args)
    warnings = []
    try:
        budget = float(data["budget"])
        max_kcal = float(data["max_kcal"])
    except (KeyError, TypeError, ValueError):
        print(json.dumps({"error": "budget 和 max_kcal 为必填数值字段"},
                         ensure_ascii=False))
        sys.exit(2)

    top_n = args.top if args.top is not None else int(data.get("top", 3))
    prefer = (args.prefer or str(data.get("prefer", "balanced"))).lower()

    items = normalize_items(data.get("items", []), warnings)
    pool = build_pool(items)
    if not pool["main"]:
        print(json.dumps({"error": "没有可用的主餐(main)商品",
                          "warnings": warnings}, ensure_ascii=False))
        sys.exit(3)

    # 组合结构：1 主餐 + 0-1 小食 + 0-1 饮品
    combos = []
    for m in pool["main"]:
        for s in pool["snack"] + [None]:
            for d in pool["drink"] + [None]:
                combo = [m] + ([s] if s else []) + ([d] if d else [])
                price = sum(x["price"] for x in combo)
                kcal = sum(x["kcal"] for x in combo)
                if price > budget or kcal > max_kcal:
                    continue
                key, price, kcal, protein = score_combo(
                    combo, budget, max_kcal, prefer)
                combos.append({
                    "items": [{"name": x["name"], "price": x["price"],
                               "kcal": x["kcal"]} for x in combo],
                    "total_price": round(price, 2),
                    "total_kcal": int(kcal),
                    "protein": round(protein, 1),
                    "budget_left": round(budget - price, 2),
                    "kcal_left": int(max_kcal - kcal),
                    "_key": key,
                })

    if not combos:
        print(json.dumps({
            "error": "无可行组合：预算或热量上限过紧，建议放宽约束或去掉小食/饮品",
            "warnings": warnings}, ensure_ascii=False))
        sys.exit(3)

    combos.sort(key=lambda c: c["_key"])
    for c in combos:
        c.pop("_key")

    print(json.dumps({"combos": combos[:top_n], "warnings": warnings,
                      "prefer": prefer}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
