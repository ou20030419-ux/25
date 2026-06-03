from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from .config import EXPIRY_LABELS, SALES_BASE_LABEL, THRESHOLDS
from .matching import build_products, match_plan
from .validation import clean_inventory, clean_plan, empty_issues, issues_frame


@dataclass
class AnalysisResult:
    products: pd.DataFrame
    anomalies: pd.DataFrame
    expiry_batches: pd.DataFrame
    plan_review: pd.DataFrame
    missed_orders: pd.DataFrame
    quality_issues: pd.DataFrame
    counts: dict[str, int]
    plan_uploaded: bool


def _sellable_periods(stock: float, sales: float) -> float:
    return stock / sales


def _expiry_category(expiry_date: pd.Timestamp, analysis_date: date) -> str | None:
    days = (expiry_date.date() - analysis_date).days
    if days <= 0:
        return "已到期"
    if days <= THRESHOLDS["7天内临期"]:
        return "7天内临期"
    if days <= THRESHOLDS["30天内临期"]:
        return "8至30天临期"
    return None


def _calculate_expiry(
    batches: pd.DataFrame, products: pd.DataFrame, analysis_date: date
) -> tuple[pd.DataFrame, pd.DataFrame]:
    details: list[dict[str, Any]] = []
    product_lookup = products.set_index("商品键")
    for _, batch in batches.iterrows():
        if batch["_身份阻断"] or not batch["_当前库存有效"] or not batch["_到期日期有效"]:
            continue
        if float(batch["批次库存"]) <= 0:
            continue
        key = batch["商品键"]
        if key not in product_lookup.index:
            continue
        product = product_lookup.loc[key]
        if product["身份状态"] != "正常" or not product["单位有效"]:
            continue
        label = _expiry_category(batch["到期日"], analysis_date)
        if label:
            details.append(
                {
                    "商品键": key,
                    "商品名": product["商品名"],
                    "条码": product["条码"],
                    "品类": product["品类"],
                    "进货日期": (
                        batch["_进货日期"].date()
                        if batch["_进货日期有效"]
                        else ""
                    ),
                    "保质期（天）": (
                        int(batch["_保质期天数"])
                        if batch["_保质期有效"]
                        else ""
                    ),
                    "货架位置": batch["货架位置"],
                    "仓库位置": batch.get("仓库位置", ""),
                    "批次库存": float(batch["批次库存"]),
                    "单位": product["单位"],
                    "到期日期": batch["到期日"].date(),
                    "到期日来源": batch["_到期日来源"],
                    "距到期天数": (batch["到期日"].date() - analysis_date).days,
                    "临期类型": label,
                    "原始行号": int(batch["原始行号"]),
                }
            )
    expiry = pd.DataFrame(
        details,
        columns=[
            "商品键",
            "商品名",
            "条码",
            "品类",
            "进货日期",
            "保质期（天）",
            "货架位置",
            "仓库位置",
            "批次库存",
            "单位",
            "到期日期",
            "到期日来源",
            "距到期天数",
            "临期类型",
            "原始行号",
        ],
    )
    if not expiry.empty:
        expiry = expiry.sort_values(["到期日期", "商品名"], kind="stable").reset_index(drop=True)
    updated = products.copy()
    for label in EXPIRY_LABELS:
        updated[f"{label}库存"] = 0.0
    if not expiry.empty:
        totals = expiry.pivot_table(
            index="商品键", columns="临期类型", values="批次库存", aggfunc="sum", fill_value=0
        )
        earliest = expiry.groupby("商品键")["到期日期"].min()
        for key in totals.index:
            for label in EXPIRY_LABELS:
                if label in totals.columns:
                    updated.loc[updated["商品键"] == key, f"{label}库存"] = float(
                        totals.at[key, label]
                    )
        updated["最早到期日"] = updated["商品键"].map(earliest)
    updated["存在临期库存"] = updated[[f"{label}库存" for label in EXPIRY_LABELS]].sum(axis=1) > 0
    return updated, expiry


def _inventory_risks(products: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, product in products.iterrows():
        risk_types: list[str] = []
        reasons: list[str] = []
        periods: float | str | Any = pd.NA
        can_calculate = (
            product["身份状态"] == "正常"
            and product["库存有效"]
            and product["本进货周期销量有效"]
            and product["单位有效"]
        )
        if can_calculate:
            sales = float(product["本进货周期销量"])
            stock = float(product["库存剩余量"])
            if sales > 0:
                periods = _sellable_periods(stock, sales)
                if periods <= THRESHOLDS["快缺货可售周期数"]:
                    risk_types.append("快缺货")
                    reasons.append(
                        f"按{SALES_BASE_LABEL} {sales:g} 估算，预计可售 {periods:.1f} 个进货周期，不超过 1 个周期"
                    )
                if periods > THRESHOLDS["库存偏高可售周期数"]:
                    risk_types.append("库存偏高")
                    reasons.append(
                        f"按{SALES_BASE_LABEL} {sales:g} 估算，预计可售 {periods:.1f} 个进货周期，超过 4 个周期"
                    )
            elif stock > 0:
                periods = "无法消化"
                risk_types.append("疑似滞销")
                reasons.append(f"{SALES_BASE_LABEL}为 0 且仍有库存")

        if product["存在临期库存"]:
            risk_types.append("临期风险")
            expiry_text = "；".join(
                f"{label} {product[f'{label}库存']:g}"
                for label in EXPIRY_LABELS
                if product[f"{label}库存"] > 0
            )
            reasons.append(expiry_text)

        if risk_types:
            row = product.to_dict()
            row.update(
                {
                    "销量计算基准": "一次进货周期",
                    "预计可售进货周期数": periods,
                    "风险类型": "、".join(risk_types),
                    "提示依据": "；".join(reasons),
                }
            )
            rows.append(row)
    return pd.DataFrame(rows)


def _plan_review(
    products: pd.DataFrame,
    anomalies: pd.DataFrame,
    matched_plan: pd.DataFrame,
) -> pd.DataFrame:
    risk_by_key = (
        anomalies.set_index("商品键")["风险类型"].to_dict() if not anomalies.empty else {}
    )
    rows: list[dict[str, Any]] = []
    matched = matched_plan[matched_plan["商品键"] != ""]
    for key, group in matched.groupby("商品键", sort=False):
        product = products[products["商品键"] == key].iloc[0]
        valid_quantities = group[group["_计划数量有效"]]["_计划进货数量"]
        planned = float(valid_quantities.sum()) if not valid_quantities.empty else pd.NA
        has_invalid_quantity = bool((~group["_计划数量有效"]).any())
        has_invalid_unit = bool((~group["_单位可计算"]).any())
        risks: list[str] = []
        reasons: list[str] = []
        status = "可自查"
        post_stock: Any = pd.NA
        post_periods: Any = pd.NA

        if has_invalid_quantity or has_invalid_unit:
            status = "数据不足无法自查"
            risks.append("数据不足无法自查")
            if has_invalid_quantity:
                reasons.append("存在非法或缺失的计划进货数量")
            if has_invalid_unit:
                reasons.append("计划单位与库存单位不一致，需先确认换算关系")
        elif planned > 0:
            blockers = product["数据状态"] != "可分析"
            existing = risk_by_key.get(key, "")
            if "疑似滞销" in existing or "库存偏高" in existing:
                risks.append("滞销或高库存仍进货")
                reasons.append("商品已有滞销或高库存提示，本次仍计划进货")
            if product["存在临期库存"]:
                risks.append("临期库存仍进货")
                total_expiring = sum(float(product[f"{label}库存"]) for label in EXPIRY_LABELS)
                reasons.append(f"现有临期库存合计 {total_expiring:g}，建议先核对批次处理")
            if not blockers:
                post_stock = float(product["库存剩余量"]) + planned
                if float(product["本进货周期销量"]) > 0:
                    post_periods = _sellable_periods(post_stock, float(product["本进货周期销量"]))
                    if post_periods > THRESHOLDS["进货过量可售周期数"]:
                        risks.append("可能进货过量")
                        reasons.append(
                            f"按{SALES_BASE_LABEL} {float(product['本进货周期销量']):g} 估算，"
                            f"进货后预计可售 {post_periods:.1f} 个进货周期，超过 6 个周期"
                        )
            else:
                status = "数据不足无法自查"
                risks.append("数据不足无法自查")
                reasons.append(product["数据状态"])
        else:
            status = "本次不补货"

        rows.append(
            {
                "商品键": key,
                "商品名": product["商品名"],
                "条码": product["条码"],
                "品类": product["品类"],
                "单位": product["单位"],
                "上次进货总量": product["上次进货总量"],
                "库存剩余量": product["库存剩余量"],
                "仓库位置": product.get("仓库位置", ""),
                "本进货周期销量": product["本进货周期销量"],
                "计划进货数量": planned,
                "进货后库存": post_stock,
                "进货后预计可售进货周期数": post_periods,
                "匹配状态": "；".join(dict.fromkeys(group["匹配状态"])),
                "录入换算说明": "；".join(
                    dict.fromkeys(
                        str(value)
                        for value in group.get("录入换算说明", pd.Series(dtype=str)).dropna()
                        if str(value).strip()
                    )
                ),
                "自查状态": status,
                "风险类型": "、".join(dict.fromkeys(risks)),
                "提示依据": "；".join(reasons)
                or "未发现规则内风险，仍请结合实际陈列与需求复核。",
            }
        )

    unmatched = matched_plan[matched_plan["商品键"] == ""]
    for _, plan_row in unmatched.iterrows():
        rows.append(
            {
                "商品键": "",
                "商品名": plan_row["商品名"],
                "条码": plan_row["条码"],
                "品类": "",
                "单位": plan_row["单位"],
                "上次进货总量": pd.NA,
                "库存剩余量": pd.NA,
                "仓库位置": "",
                "本进货周期销量": pd.NA,
                "计划进货数量": plan_row["_计划进货数量"],
                "进货后库存": pd.NA,
                "进货后预计可售进货周期数": pd.NA,
                "匹配状态": plan_row["匹配状态"],
                "录入换算说明": plan_row.get("录入换算说明", ""),
                "自查状态": "待核对",
                "风险类型": "数据不足无法自查",
                "提示依据": "计划商品未能唯一匹配库存商品，请核对条码或商品名。",
            }
        )
    return pd.DataFrame(rows)


def _missed_orders(
    anomalies: pd.DataFrame, matched_plan: pd.DataFrame
) -> pd.DataFrame:
    if anomalies.empty:
        return pd.DataFrame()
    shortages = anomalies[anomalies["风险类型"].str.contains("快缺货", na=False)]
    rows: list[dict[str, Any]] = []
    for _, product in shortages.iterrows():
        key = product["商品键"]
        direct = matched_plan[matched_plan["商品键"] == key]
        valid_positive = direct[
            direct["_计划数量有效"] & direct["_单位可计算"] & (direct["_计划进货数量"] > 0)
        ]
        if not valid_positive.empty:
            continue
        uncertain = bool((~direct["_计划数量有效"]).any())
        uncertain = uncertain or bool((~direct["_单位可计算"]).any())
        candidate_uncertain = matched_plan[
            matched_plan["_候选商品键"].map(lambda values: key in values)
            & matched_plan["商品键"].eq("")
        ]
        uncertain = uncertain or not candidate_uncertain.empty
        row = {
            "商品名": product["商品名"],
            "条码": product["条码"],
            "品类": product["品类"],
            "上次进货总量": product["上次进货总量"],
            "库存剩余量": product["库存剩余量"],
            "仓库位置": product.get("仓库位置", ""),
            "本进货周期销量": product["本进货周期销量"],
            "预计可售进货周期数": product["预计可售进货周期数"],
            "货架位置": product["货架位置"],
            "判断状态": "待核对是否漏订" if uncertain else "可能漏订",
            "提示依据": (
                "计划行存在数量或匹配问题，需先核对后确认是否漏订。"
                if uncertain
                else f"按{SALES_BASE_LABEL}估算，预计可售不超过 1 个进货周期，且未匹配到正数计划进货量。"
            ),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def analyse(
    inventory_frame: pd.DataFrame,
    plan_frame: pd.DataFrame | None,
    analysis_date: date,
) -> AnalysisResult:
    issues = empty_issues()
    inventory = clean_inventory(inventory_frame, issues)
    products, batches = build_products(inventory, issues)
    products, expiry = _calculate_expiry(batches, products, analysis_date)
    anomalies = _inventory_risks(products)

    if plan_frame is not None:
        plan = clean_plan(plan_frame, issues)
        matched_plan = match_plan(plan, products, issues)
        plan_review = _plan_review(products, anomalies, matched_plan)
        missed = _missed_orders(anomalies, matched_plan)
    else:
        plan_review = pd.DataFrame()
        missed = pd.DataFrame()

    def risk_count(label: str) -> int:
        if anomalies.empty:
            return 0
        return int(anomalies["风险类型"].str.contains(label, na=False).sum())

    counts = {
        "快缺货": risk_count("快缺货"),
        "库存偏高": risk_count("库存偏高"),
        "疑似滞销": risk_count("疑似滞销"),
        "临期": risk_count("临期风险"),
        "进货风险": (
            int(
                plan_review[
                    plan_review["风险类型"].fillna("").str.contains(
                        "滞销或高库存仍进货|可能进货过量|临期库存仍进货"
                    )
                ].shape[0]
            )
            if not plan_review.empty
            else 0
        ),
        "可能漏订": (
            int(missed[missed["判断状态"] == "可能漏订"].shape[0])
            if not missed.empty
            else 0
        ),
    }
    return AnalysisResult(
        products=products,
        anomalies=anomalies,
        expiry_batches=expiry,
        plan_review=plan_review,
        missed_orders=missed,
        quality_issues=issues_frame(issues),
        counts=counts,
        plan_uploaded=plan_frame is not None,
    )
