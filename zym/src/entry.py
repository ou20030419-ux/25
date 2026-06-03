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
    "每进货单位折合库存单位数量",
    "库存单位",
    "备注",
]
DIRECT_INVENTORY_COLUMNS = [
    "商品名",
    "进货日期",
    "上次进货总量",
    "本进货周期销量",
    "库存剩余量",
    "单位",
    "近30天销量",
    "保质期（天）",
    "标注到期日期",
    "货架位置",
    "仓库位置",
    "条码",
    "品类",
]


def blank_entry_frame(columns: list[str], rows: int) -> pd.DataFrame:
    return pd.DataFrame([{column: "" for column in columns} for _ in range(rows)])


def compact_entry_frame(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    ignored_values = {UNIT_PLACEHOLDER, CUSTOM_UNIT}
    populated = data.fillna("").astype(str).apply(
        lambda row: any(value.strip() and value.strip() not in ignored_values for value in row),
        axis=1,
    )
    return data.loc[populated].reset_index(drop=True)


def resolve_unit(selected: object, custom: object = "") -> str:
    chosen = "" if pd.isna(selected) else str(selected).strip()
    manual = "" if pd.isna(custom) else str(custom).strip()
    if manual:
        return manual
    if chosen == UNIT_PLACEHOLDER:
        return ""
    if chosen == CUSTOM_UNIT:
        return ""
    return chosen


def _series_or_default(frame: pd.DataFrame, column: str, default: object = "") -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series([default] * len(frame), index=frame.index)


def inventory_editor_frame(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if "标注到期日期" not in data.columns and "到期日期" in data.columns:
        data["标注到期日期"] = data["到期日期"]
    if "本进货周期销量" not in data.columns and "近7天销量" in data.columns:
        data["本进货周期销量"] = data["近7天销量"]
    if "库存剩余量" not in data.columns and "当前库存" in data.columns:
        data["库存剩余量"] = data["当前库存"]
    for column in INVENTORY_COLUMNS:
        if column not in data.columns:
            data[column] = ""
    if "自定义单位" not in data.columns:
        data["自定义单位"] = ""
    data["单位"] = [
        resolve_unit(unit, custom)
        for unit, custom in zip(data["单位"], data["自定义单位"])
    ]
    return data[DIRECT_INVENTORY_COLUMNS].reset_index(drop=True)


def _merged_plan_unit(frame: pd.DataFrame, unit_column: str, custom_column: str) -> pd.Series:
    units = _series_or_default(frame, unit_column)
    custom_units = _series_or_default(frame, custom_column)
    return pd.Series(
        [resolve_unit(unit, custom) for unit, custom in zip(units, custom_units)],
        index=frame.index,
    )


def plan_editor_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        data = blank_entry_frame(DIRECT_PLAN_COLUMNS, 10)
    else:
        data = pd.DataFrame(columns=DIRECT_PLAN_COLUMNS)
        data["商品名"] = _series_or_default(frame, "商品名")
        data["条码"] = _series_or_default(frame, "条码")
        data["计划进货数量"] = _series_or_default(frame, "计划进货数量")
        data["进货单位"] = (
            _merged_plan_unit(frame, "进货单位", "自定义进货单位")
            if "进货单位" in frame.columns
            else _series_or_default(frame, "单位")
        )
        data["每进货单位折合库存单位数量"] = _series_or_default(
            frame, "每进货单位折合库存单位数量", 1
        )
        data["库存单位"] = (
            _merged_plan_unit(frame, "库存单位", "自定义库存单位")
            if "库存单位" in frame.columns
            else _series_or_default(frame, "单位")
        )
        data["备注"] = _series_or_default(frame, "备注")
    return data.reset_index(drop=True)


def submitted_inventory(frame: pd.DataFrame) -> pd.DataFrame:
    compact = compact_entry_frame(frame)
    if compact.empty:
        return compact
    if "自定义单位" not in compact.columns:
        compact["自定义单位"] = ""
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
        order_unit = resolve_unit(row["进货单位"], row.get("自定义进货单位", ""))
        stock_unit = resolve_unit(row["库存单位"], row.get("自定义库存单位", ""))
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
