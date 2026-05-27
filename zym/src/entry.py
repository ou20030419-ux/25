from __future__ import annotations

import pandas as pd

from .config import INVENTORY_COLUMNS

UNIT_PLACEHOLDER = "请选择单位"
UNIT_OPTIONS = [
    UNIT_PLACEHOLDER,
    "瓶",
    "罐",
    "听",
    "袋",
    "包",
    "盒",
    "个",
    "根",
    "支",
    "杯",
    "桶",
    "箱",
    "提",
    "板",
    "件",
    "克",
    "千克",
    "其他（手动填写）",
]
CUSTOM_UNIT = "其他（手动填写）"
DIRECT_PLAN_COLUMNS = [
    "商品名",
    "条码",
    "计划进货数量",
    "进货单位",
    "自定义进货单位",
    "每进货单位折合库存单位数量",
    "库存单位",
    "自定义库存单位",
    "备注",
]
DIRECT_INVENTORY_COLUMNS = [
    "商品名",
    "进货日期",
    "当前库存",
    "单位",
    "近7天销量",
    "近30天销量",
    "保质期（天）",
    "标注到期日期",
    "货架位置",
    "条码",
    "品类",
    "自定义单位",
]


def blank_entry_frame(columns: list[str], rows: int) -> pd.DataFrame:
    return pd.DataFrame([{column: "" for column in columns} for _ in range(rows)])


def compact_entry_frame(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    populated = data.fillna("").astype(str).apply(
        lambda row: any(value.strip() and value.strip() != UNIT_PLACEHOLDER for value in row),
        axis=1,
    )
    return data.loc[populated].reset_index(drop=True)


def resolve_unit(selected: object, custom: object) -> str:
    chosen = "" if pd.isna(selected) else str(selected).strip()
    manual = "" if pd.isna(custom) else str(custom).strip()
    if chosen == UNIT_PLACEHOLDER:
        return ""
    return manual if chosen == CUSTOM_UNIT else chosen


def inventory_editor_frame(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if "标注到期日期" not in data.columns and "到期日期" in data.columns:
        data["标注到期日期"] = data["到期日期"]
    for column in INVENTORY_COLUMNS:
        if column not in data.columns:
            data[column] = ""
    if "自定义单位" not in data.columns:
        data["自定义单位"] = ""
    data["单位"] = data["单位"].map(
        lambda value: UNIT_PLACEHOLDER if pd.isna(value) or not str(value).strip() else value
    )
    return data[DIRECT_INVENTORY_COLUMNS].reset_index(drop=True)


def plan_editor_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if set(DIRECT_PLAN_COLUMNS).issubset(frame.columns):
        data = frame[DIRECT_PLAN_COLUMNS].copy()
    elif frame.empty:
        data = blank_entry_frame(DIRECT_PLAN_COLUMNS, 10)
    else:
        data = pd.DataFrame(columns=DIRECT_PLAN_COLUMNS)
        data["商品名"] = frame.get("商品名", "")
        data["条码"] = frame.get("条码", "")
        data["计划进货数量"] = frame.get("计划进货数量", "")
        data["进货单位"] = frame.get("单位", "")
        data["自定义进货单位"] = ""
        data["每进货单位折合库存单位数量"] = 1
        data["库存单位"] = frame.get("单位", "")
        data["自定义库存单位"] = ""
        data["备注"] = frame.get("备注", "")
    for column in ["进货单位", "库存单位"]:
        data[column] = data[column].map(
            lambda value: UNIT_PLACEHOLDER if pd.isna(value) or not str(value).strip() else value
        )
    return data.reset_index(drop=True)


def submitted_inventory(frame: pd.DataFrame) -> pd.DataFrame:
    compact = compact_entry_frame(frame)
    if compact.empty:
        return compact
    compact["单位"] = compact.apply(
        lambda row: resolve_unit(row["单位"], row["自定义单位"]), axis=1
    )
    return compact[INVENTORY_COLUMNS]


def submitted_plan(frame: pd.DataFrame) -> pd.DataFrame | None:
    compact = compact_entry_frame(frame)
    if compact.empty:
        return None
    rows: list[dict[str, object]] = []
    for _, row in compact.iterrows():
        order_unit = resolve_unit(row["进货单位"], row["自定义进货单位"])
        stock_unit = resolve_unit(row["库存单位"], row["自定义库存单位"])
        quantity = pd.to_numeric(row["计划进货数量"], errors="coerce")
        factor_text = "" if pd.isna(row["每进货单位折合库存单位数量"]) else str(
            row["每进货单位折合库存单位数量"]
        ).strip()
        factor = pd.to_numeric(factor_text, errors="coerce") if factor_text else (
            1 if order_unit == stock_unit and order_unit else pd.NA
        )
        can_convert = (
            pd.notna(quantity)
            and pd.notna(factor)
            and float(factor) > 0
            and bool(order_unit)
            and bool(stock_unit)
        )
        converted_quantity: object = float(quantity) * float(factor) if can_convert else ""
        analysis_unit = stock_unit if can_convert else order_unit
        conversion_note = ""
        if can_convert:
            conversion_note = (
                f"{float(quantity):g} {order_unit} x {float(factor):g} = "
                f"{float(converted_quantity):g} {stock_unit}"
            )
        elif order_unit != stock_unit:
            conversion_note = "进货单位与库存单位不同，请填写有效换算数量后重新提交。"
        rows.append(
            {
                "商品名": row["商品名"],
                "条码": row["条码"],
                "计划进货数量": converted_quantity,
                "单位": analysis_unit,
                "备注": row["备注"],
                "录入换算说明": conversion_note,
            }
        )
    return pd.DataFrame(rows)
