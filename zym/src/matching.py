from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from .validation import add_issue, display_value


def _joined(values: pd.Series) -> str:
    items = [display_value(value) for value in values if display_value(value)]
    return "、".join(dict.fromkeys(items))


def build_products(
    inventory: pd.DataFrame, issues: list[dict[str, Any]]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = inventory.copy()
    data["_身份阻断"] = ~data["_身份有效"]

    named_barcodes = data[(data["_条码"] != "") & (data["_名称"] != "")]
    for barcode, group in named_barcodes.groupby("_条码"):
        if group["_名称"].nunique() > 1:
            data.loc[group.index, "_身份阻断"] = True
            for _, row in group.iterrows():
                add_issue(
                    issues,
                    "条码身份冲突",
                    "库存销售表",
                    int(row["_原始行号"]),
                    row["商品名"],
                    row["条码"],
                    "同一条码对应多个不同商品名，相关行暂不参与自动分析。",
                )

    valid_named = data[
        (~data["_身份阻断"]) & (data["_条码"] != "") & (data["_名称"] != "")
    ]
    name_to_barcodes = (
        valid_named.groupby("_名称")["_条码"].apply(lambda values: set(values)).to_dict()
    )

    data["_商品键"] = ""
    for index, row in data.iterrows():
        if row["_身份阻断"]:
            data.at[index, "_商品键"] = f"待核对:{int(row['_原始行号'])}"
        elif row["_条码"]:
            data.at[index, "_商品键"] = f"条码:{row['_条码']}"
        else:
            candidate_barcodes = name_to_barcodes.get(row["_名称"], set())
            if len(candidate_barcodes) == 1:
                data.at[index, "_商品键"] = f"条码:{next(iter(candidate_barcodes))}"
            elif len(candidate_barcodes) > 1:
                data.at[index, "_身份阻断"] = True
                data.at[index, "_商品键"] = f"待核对:{int(row['_原始行号'])}"
                add_issue(
                    issues,
                    "名称匹配歧义",
                    "库存销售表",
                    int(row["_原始行号"]),
                    row["商品名"],
                    row["条码"],
                    "该商品名对应多个条码，无条码批次不能自动归并。",
                )
            else:
                data.at[index, "_商品键"] = f"名称:{row['_名称']}"

    product_rows: list[dict[str, Any]] = []
    for key, group in data.groupby("_商品键", sort=False):
        identity_ok = not group["_身份阻断"].any()
        units = [value for value in group["单位"].map(display_value).unique() if value]
        unit_ok = len(units) == 1
        if not units:
            for _, row in group.iterrows():
                add_issue(
                    issues,
                    "单位缺失",
                    "库存销售表",
                    int(row["_原始行号"]),
                    row["商品名"],
                    row["条码"],
                    "请为库存剩余量与销量选择统一单位后重新分析。",
                )
        elif not unit_ok:
            for _, row in group.iterrows():
                add_issue(
                    issues,
                    "单位不一致",
                    "库存销售表",
                    int(row["_原始行号"]),
                    row["商品名"],
                    row["条码"],
                    "同一商品存在多个单位，未提供换算关系前不进行数量分析。",
                )
        stock_ok = bool(group["_库存剩余量有效"].all()) and unit_ok and identity_ok
        stock = group["_库存剩余量"].sum() if stock_ok else pd.NA
        purchase_total_ok = bool(group["_上次进货总量有效"].all()) and unit_ok and identity_ok
        purchase_total = group["_上次进货总量"].sum() if purchase_total_ok else pd.NA

        sales_values: dict[str, Any] = {}
        sales_ok: dict[str, bool] = {}
        for column in ["本进货周期销量", "近30天销量"]:
            values_valid = bool(group[f"_{column}有效"].all())
            unique_values = group.loc[group[f"_{column}有效"], f"_{column}"].dropna().unique()
            consistent = len(unique_values) <= 1
            if values_valid and not consistent:
                for _, row in group.iterrows():
                    add_issue(
                        issues,
                        "销量冲突",
                        "库存销售表",
                        int(row["_原始行号"]),
                        row["商品名"],
                        row["条码"],
                        f"同商品不同批次的“{column}”填写不一致，不生成依赖销量的结论。",
                    )
            sales_ok[column] = values_valid and consistent and identity_ok and unit_ok
            sales_values[column] = (
                float(unique_values[0]) if sales_ok[column] and len(unique_values) == 1 else pd.NA
            )

        statuses: list[str] = []
        if not identity_ok:
            statuses.append("身份待核对")
        if not unit_ok:
            statuses.append("单位待核对")
        if not stock_ok:
            statuses.append("库存待核对")
        if not sales_ok["本进货周期销量"]:
            statuses.append("本进货周期销量待核对")

        barcodes = [value for value in group["_条码"].unique() if value]
        product_rows.append(
            {
                "商品键": key,
                "商品名": _joined(group["商品名"]),
                "条码": barcodes[0] if len(barcodes) == 1 else "",
                "品类": _joined(group["品类"]),
                "单位": "、".join(units),
                "上次进货总量": purchase_total,
                "库存剩余量": stock,
                "当前库存": stock,
                "本进货周期销量": sales_values["本进货周期销量"],
                "近30天销量": sales_values["近30天销量"],
                "货架位置": _joined(group["货架位置"]),
                "仓库位置": _joined(group["仓库位置"]) if "仓库位置" in group.columns else "",
                "最早到期日": pd.NaT,
                "身份状态": "正常" if identity_ok else "待核对",
                "库存有效": stock_ok,
                "本进货周期销量有效": sales_ok["本进货周期销量"],
                "单位有效": unit_ok,
                "库存剩余量来源": "；".join(
                    dict.fromkeys(
                        str(value)
                        for value in group.get("_库存剩余量来源", pd.Series(dtype=str)).dropna()
                        if str(value).strip()
                    )
                ),
                "数据状态": "可分析" if not statuses else "；".join(statuses),
                "_名称集合": tuple(value for value in group["_名称"].unique() if value),
                "_源行号": tuple(int(value) for value in group["_原始行号"]),
            }
        )

    products = pd.DataFrame(product_rows)
    batches = data.rename(
        columns={
            "_商品键": "商品键",
            "_当前库存": "批次库存",
            "_到期日期": "到期日",
            "_原始行号": "原始行号",
        }
    )
    return products, batches


def match_plan(
    plan: pd.DataFrame, products: pd.DataFrame, issues: list[dict[str, Any]]
) -> pd.DataFrame:
    eligible = products[products["身份状态"] == "正常"]
    barcode_to_keys: dict[str, list[str]] = defaultdict(list)
    name_to_keys: dict[str, list[str]] = defaultdict(list)
    for _, product in eligible.iterrows():
        if product["条码"]:
            barcode_to_keys[product["条码"]].append(product["商品键"])
        for name in product["_名称集合"]:
            name_to_keys[name].append(product["商品键"])

    result = plan.copy()
    result["商品键"] = ""
    result["匹配状态"] = ""
    result["_单位可计算"] = True
    result["_候选商品键"] = [tuple() for _ in range(len(result))]
    for index, row in result.iterrows():
        candidates: list[str] = []
        if not row["_身份有效"]:
            result.at[index, "匹配状态"] = "无有效商品识别信息"
        elif row["_条码"]:
            candidates = barcode_to_keys.get(row["_条码"], [])
            if len(candidates) == 1:
                result.at[index, "商品键"] = candidates[0]
                result.at[index, "匹配状态"] = "已按条码匹配"
            else:
                result.at[index, "匹配状态"] = "条码未匹配库存商品"
                add_issue(
                    issues,
                    "计划商品未匹配",
                    "计划进货单",
                    int(row["_原始行号"]),
                    row["商品名"],
                    row["条码"],
                    "计划单条码在可分析库存商品中未找到，请核对条码录入。",
                    False,
                )
        else:
            candidates = list(dict.fromkeys(name_to_keys.get(row["_名称"], [])))
            if len(candidates) == 1:
                result.at[index, "商品键"] = candidates[0]
                result.at[index, "匹配状态"] = "已按商品名匹配"
            elif len(candidates) > 1:
                result.at[index, "匹配状态"] = "名称匹配歧义"
                add_issue(
                    issues,
                    "名称匹配歧义",
                    "计划进货单",
                    int(row["_原始行号"]),
                    row["商品名"],
                    row["条码"],
                    "无条码计划行对应多个库存商品，不能自动匹配。",
                )
            else:
                result.at[index, "匹配状态"] = "商品名未匹配库存商品"
                add_issue(
                    issues,
                    "计划商品未匹配",
                    "计划进货单",
                    int(row["_原始行号"]),
                    row["商品名"],
                    row["条码"],
                    "计划单商品名在可分析库存商品中未找到。",
                    False,
                )
        result.at[index, "_候选商品键"] = tuple(candidates)
        key = result.at[index, "商品键"]
        if key:
            inventory_unit = display_value(
                products.loc[products["商品键"] == key, "单位"].iloc[0]
            )
            plan_unit = display_value(row["单位"])
            if not plan_unit:
                result.at[index, "_单位可计算"] = False
                result.at[index, "匹配状态"] = f"{result.at[index, '匹配状态']}；单位缺失待核对"
                add_issue(
                    issues,
                    "单位缺失",
                    "计划进货单",
                    int(row["_原始行号"]),
                    row["商品名"],
                    row["条码"],
                    "请填写计划进货单位；如与库存单位不同，还需确认换算关系。",
                )
            elif inventory_unit and inventory_unit != plan_unit:
                result.at[index, "_单位可计算"] = False
                result.at[index, "匹配状态"] = f"{result.at[index, '匹配状态']}；单位不一致待核对"
                add_issue(
                    issues,
                    "单位不一致",
                    "计划进货单",
                    int(row["_原始行号"]),
                    row["商品名"],
                    row["条码"],
                    f"计划单位“{plan_unit}”与库存单位“{inventory_unit}”不同，未提供换算关系。",
                )
    return result
