from zoneinfo import ZoneInfo

RULESET_VERSION = "MVP_RULESET_V2"
STORE_TIMEZONE = ZoneInfo("Asia/Shanghai")

THRESHOLDS = {
    "快缺货可售天数": 3,
    "库存偏高可售天数": 30,
    "进货过量可售天数": 45,
    "7天内临期": 7,
    "30天内临期": 30,
}

INVENTORY_COLUMNS = [
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
]

PLAN_COLUMNS = ["商品名", "条码", "计划进货数量", "单位", "备注"]

ISSUE_COLUMNS = [
    "严重程度",
    "问题类型",
    "所在文件",
    "原始行号",
    "商品名",
    "条码",
    "问题说明",
    "处理状态",
]

EXPIRY_LABELS = ["已到期", "7天内临期", "8至30天临期"]
