import re
from typing import Any

import pandas as pd

from .config import INVENTORY_COLUMNS, ISSUE_COLUMNS, PLAN_COLUMNS


def empty_issues() -> list[dict[str, Any]]:
    return []


def issues_frame(issues: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(issues, columns=ISSUE_COLUMNS)


def add_issue(
    issues: list[dict[str, Any]],
    issue_type: str,
    source: str,
    row: Any,
    name: Any,
    barcode: Any,
    detail: str,
    blocking: bool = True,
) -> None:
    issues.append(
        {
            "严重程度": "需先核对" if blocking else "提示",
            "问题类型": issue_type,
            "所在文件": source,
            "原始行号": row if row is not None else "-",
            "商品名": display_value(name),
            "条码": display_value(barcode),
            "问题说明": detail,
            "处理状态": "阻断相关自动分析" if blocking else "保留可用分析",
        }
    )


def display_value(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def normalize_name(value: Any) -> str:
    return re.sub(r"\s+", " ", display_value(value)).strip().casefold()


def normalize_barcode(value: Any) -> tuple[str, str | None]:
    text = display_value(value)
    if not text:
        return "", None
    if re.search(r"[eE][+-]?\d+$", text) or re.fullmatch(r"\d+\.0+", text):
        return "", "条码呈数值或科学计数法格式，可能已丢失前导零"
    return text, None


def _ensure_columns(
    frame: pd.DataFrame,
    columns: list[str],
    required: list[str],
    source: str,
    issues: list[dict[str, Any]],
    report_optional_missing: bool = True,
) -> pd.DataFrame:
    data = frame.copy()
    for column in columns:
        if column not in data.columns:
            data[column] = pd.NA
            if column in required or report_optional_missing:
                add_issue(
                    issues,
                    "缺失字段",
                    source,
                    None,
                    "",
                    "",
                    f"未提供“{column}”字段。",
                    column in required,
                )
    return data


def _parse_number(
    value: Any,
    column: str,
    source: str,
    row: int,
    name: Any,
    barcode: Any,
    issues: list[dict[str, Any]],
    blocking: bool = True,
) -> tuple[float | None, bool]:
    text = display_value(value)
    if not text:
        add_issue(
            issues,
            "数量或销量缺失",
            source,
            row,
            name,
            barcode,
            f"“{column}”为空。",
            blocking,
        )
        return None, False
    number = pd.to_numeric(text.replace(",", ""), errors="coerce")
    if pd.isna(number) or float(number) < 0:
        add_issue(
            issues,
            "非法数量或销量",
            source,
            row,
            name,
            barcode,
            f"“{column}”值“{text}”不是有效的非负数。",
            blocking,
        )
        return None, False
    return float(number), True


def clean_inventory(frame: pd.DataFrame, issues: list[dict[str, Any]]) -> pd.DataFrame:
    source = "库存销售表"
    source_data = frame.copy()
    if "标注到期日期" not in source_data.columns and "到期日期" in source_data.columns:
        source_data["标注到期日期"] = source_data["到期日期"]
    if "本进货周期销量" not in source_data.columns and "近7天销量" in source_data.columns:
        source_data["本进货周期销量"] = source_data["近7天销量"]
    if "库存剩余量" not in source_data.columns and "当前库存" in source_data.columns:
        source_data["库存剩余量"] = source_data["当前库存"]
    received_columns = set(source_data.columns)
    data = _ensure_columns(
        source_data,
        INVENTORY_COLUMNS,
        ["本进货周期销量"],
        source,
        issues,
        report_optional_missing=False,
    )
    data = data.reset_index(drop=True)
    data["_原始行号"] = data.index + 2
    data["_原始商品名"] = data["商品名"].map(display_value)
    data["_原始条码"] = data["条码"].map(display_value)
    data["_名称"] = data["商品名"].map(normalize_name)

    barcodes = data["条码"].map(normalize_barcode)
    data["_条码"] = [result[0] for result in barcodes]
    for index, (_, warning) in enumerate(barcodes):
        if warning:
            add_issue(
                issues,
                "条码格式待核对",
                source,
                int(data.at[index, "_原始行号"]),
                data.at[index, "商品名"],
                data.at[index, "条码"],
                warning,
            )

    data["_身份有效"] = True
    for index, row in data.iterrows():
        if not row["_条码"] and not row["_名称"]:
            data.at[index, "_身份有效"] = False
            add_issue(
                issues,
                "无识别字段",
                source,
                int(row["_原始行号"]),
                row["商品名"],
                row["条码"],
                "商品名与有效条码均为空，无法识别商品。",
            )

    for column in ["上次进货总量", "本进货周期销量", "库存剩余量", "近30天销量"]:
        parsed: list[float | None] = []
        valid: list[bool] = []
        if column not in received_columns:
            data[f"_{column}"] = [None] * len(data)
            data[f"_{column}有效"] = [False] * len(data)
            continue
        for _, row in data.iterrows():
            blocking = column in {"本进货周期销量"}
            if not blocking and not display_value(row[column]):
                parsed.append(None)
                valid.append(False)
                continue
            number, ok = _parse_number(
                row[column],
                column,
                source,
                int(row["_原始行号"]),
                row["商品名"],
                row["条码"],
                issues,
                blocking,
            )
            parsed.append(number)
            valid.append(ok)
        data[f"_{column}"] = parsed
        data[f"_{column}有效"] = valid

    stock_values: list[float | None] = []
    stock_valid: list[bool] = []
    stock_sources: list[str] = []
    for index, row in data.iterrows():
        if row["_库存剩余量有效"]:
            stock_values.append(float(row["_库存剩余量"]))
            stock_valid.append(True)
            stock_sources.append("手动填写库存剩余量")
            continue
        if row["_上次进货总量有效"] and row["_本进货周期销量有效"]:
            remaining = float(row["_上次进货总量"]) - float(row["_本进货周期销量"])
            if remaining < 0:
                add_issue(
                    issues,
                    "库存剩余量异常",
                    source,
                    int(row["_原始行号"]),
                    row["商品名"],
                    row["条码"],
                    "本进货周期销量大于上次进货总量，库存剩余量按 0 参与分析；请核对是否存在上期库存或录入错误。",
                    False,
                )
                remaining = 0.0
            stock_values.append(remaining)
            stock_valid.append(True)
            stock_sources.append("按上次进货总量-本进货周期销量计算")
            data.at[index, "库存剩余量"] = remaining
            continue
        stock_values.append(None)
        stock_valid.append(False)
        stock_sources.append("")
        add_issue(
            issues,
            "库存剩余量缺失",
            source,
            int(row["_原始行号"]),
            row["商品名"],
            row["条码"],
            "请填写库存剩余量，或同时填写上次进货总量和本进货周期销量以便系统自动计算。",
        )
    data["_库存剩余量"] = stock_values
    data["_库存剩余量有效"] = stock_valid
    data["_库存剩余量来源"] = stock_sources
    data["_当前库存"] = data["_库存剩余量"]
    data["_当前库存有效"] = data["_库存剩余量有效"]
    data["当前库存"] = data["库存剩余量"]

    parsed_arrivals = pd.to_datetime(data["进货日期"], errors="coerce")
    data["_进货日期"] = parsed_arrivals
    data["_进货日期有效"] = parsed_arrivals.notna()
    parsed_label_expiries = pd.to_datetime(data["标注到期日期"], errors="coerce")
    data["_标注到期日期"] = parsed_label_expiries
    data["_标注到期日期有效"] = parsed_label_expiries.notna()
    for index, row in data.iterrows():
        for column, parsed_column in [
            ("进货日期", "_进货日期"),
            ("标注到期日期", "_标注到期日期"),
        ]:
            text = display_value(row[column])
            if not text or pd.notna(row[parsed_column]):
                continue
            add_issue(
                issues,
                "无效日期",
                source,
                int(row["_原始行号"]),
                row["商品名"],
                row["条码"],
                f"{column}“{text}”无法识别。",
                False,
            )

    shelf_life_days: list[float | None] = []
    shelf_life_valid: list[bool] = []
    for _, row in data.iterrows():
        text = display_value(row["保质期（天）"])
        if not text:
            shelf_life_days.append(None)
            shelf_life_valid.append(False)
            continue
        number = pd.to_numeric(text, errors="coerce")
        valid = pd.notna(number) and float(number) > 0 and float(number).is_integer()
        if not valid:
            add_issue(
                issues,
                "无效保质期",
                source,
                int(row["_原始行号"]),
                row["商品名"],
                row["条码"],
                f"保质期（天）“{text}”应填写正整数天数。",
                False,
            )
        shelf_life_days.append(float(number) if valid else None)
        shelf_life_valid.append(bool(valid))
    data["_保质期天数"] = shelf_life_days
    data["_保质期有效"] = shelf_life_valid
    data["_到期日期"] = pd.NaT
    data["_到期日来源"] = ""

    for index, row in data.iterrows():
        labelled_expiry = row["_标注到期日期"] if row["_标注到期日期有效"] else pd.NaT
        estimated_expiry = pd.NaT
        if row["_进货日期有效"] and row["_保质期有效"]:
            estimated_expiry = row["_进货日期"] + pd.to_timedelta(row["_保质期天数"], unit="D")
        if pd.notna(labelled_expiry):
            data.at[index, "_到期日期"] = labelled_expiry
            data.at[index, "_到期日来源"] = "包装标注到期日"
            if pd.notna(estimated_expiry) and labelled_expiry.date() != estimated_expiry.date():
                add_issue(
                    issues,
                    "到期日期不一致",
                    source,
                    int(row["_原始行号"]),
                    row["商品名"],
                    row["条码"],
                    "包装标注到期日与按进货日期及保质期估算的日期不同，临期判断采用包装标注到期日。",
                    False,
                )
        elif pd.notna(estimated_expiry):
            data.at[index, "_到期日期"] = estimated_expiry
            data.at[index, "_到期日来源"] = "按进货日期及保质期估算"
        elif row["_当前库存有效"] and float(row["_当前库存"]) > 0:
            add_issue(
                issues,
                "临期信息不足",
                source,
                int(row["_原始行号"]),
                row["商品名"],
                row["条码"],
                "有库存但无法判断临期；请填写标注到期日期，或同时填写进货日期与保质期（天）。",
                False,
            )
    data["_到期日期有效"] = data["_到期日期"].notna()
    return data


def clean_plan(frame: pd.DataFrame, issues: list[dict[str, Any]]) -> pd.DataFrame:
    source = "计划进货单"
    received_columns = set(frame.columns)
    data = _ensure_columns(frame, PLAN_COLUMNS, ["计划进货数量"], source, issues)
    data = data.reset_index(drop=True)
    data["_原始行号"] = data.index + 2
    data["_原始商品名"] = data["商品名"].map(display_value)
    data["_原始条码"] = data["条码"].map(display_value)
    data["_名称"] = data["商品名"].map(normalize_name)
    barcodes = data["条码"].map(normalize_barcode)
    data["_条码"] = [result[0] for result in barcodes]
    data["_身份有效"] = True
    for index, (_, warning) in enumerate(barcodes):
        if warning:
            add_issue(
                issues,
                "条码格式待核对",
                source,
                int(data.at[index, "_原始行号"]),
                data.at[index, "商品名"],
                data.at[index, "条码"],
                warning,
            )
    for index, row in data.iterrows():
        if not row["_条码"] and not row["_名称"]:
            data.at[index, "_身份有效"] = False
            add_issue(
                issues,
                "无识别字段",
                source,
                int(row["_原始行号"]),
                row["商品名"],
                row["条码"],
                "商品名与有效条码均为空，无法匹配计划商品。",
            )
        if "计划进货数量" in received_columns:
            quantity, valid = _parse_number(
                row["计划进货数量"],
                "计划进货数量",
                source,
                int(row["_原始行号"]),
                row["商品名"],
                row["条码"],
                issues,
            )
        else:
            quantity, valid = None, False
        data.at[index, "_计划进货数量"] = quantity
        data.at[index, "_计划数量有效"] = valid
    data["_计划数量有效"] = data["_计划数量有效"].eq(True)
    return data
