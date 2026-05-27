import unittest
from datetime import date, datetime
from io import BytesIO

import pandas as pd

from src.export import build_export_workbook
from src.io import read_table, template_bytes, template_frame
from src.rules import analyse


class FileAndExportTests(unittest.TestCase):
    def test_csv_encodings_are_supported(self):
        source = template_frame("inventory", True).head(1)
        for encoding in ["utf-8-sig", "utf-8", "gb18030"]:
            payload = source.to_csv(index=False).encode(encoding)
            loaded = read_table(payload, "库存.csv")
            self.assertEqual(loaded.iloc[0]["商品名"], "海盐薯片 60g")

    def test_template_preserves_barcode_as_text(self):
        bytes_value = template_bytes("inventory", sample=True)
        loaded = read_table(bytes_value, "库存.xlsx")
        self.assertEqual(loaded.iloc[0]["条码"], "6900000000012")

    def test_export_contains_traceability_sheets(self):
        result = analyse(template_frame("inventory", True), None, date(2026, 5, 25))
        workbook = build_export_workbook(
            result,
            date(2026, 5, 25),
            {"inventory": "库存.xlsx", "plan": "未上传"},
            datetime(2026, 5, 25, 10, 0),
        )
        excel = pd.ExcelFile(BytesIO(workbook))
        self.assertEqual(
            set(excel.sheet_names),
            {
                "分析说明",
                "数据质量问题",
                "异常商品清单",
                "临期批次明细",
                "进货单自查结果",
                "可能漏订清单",
            },
        )
        notes = pd.read_excel(BytesIO(workbook), sheet_name="分析说明")
        self.assertIn("MVP_RULESET_V2", set(notes["内容"]))


if __name__ == "__main__":
    unittest.main()
