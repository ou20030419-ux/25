import unittest
from datetime import date

import pandas as pd

from src.config import INVENTORY_COLUMNS
from src.entry import DIRECT_PLAN_COLUMNS, blank_entry_frame, inventory_editor_frame, submitted_inventory, submitted_plan
from src.io import template_frame
from src.rules import analyse


class DirectEntryUnitTests(unittest.TestCase):
    def test_inventory_entry_places_unit_and_expiry_fields_with_core_quantities(self):
        draft = inventory_editor_frame(template_frame("inventory").head(0))
        self.assertEqual(
            list(draft.columns[:8]),
            [
                "商品名",
                "进货日期",
                "当前库存",
                "单位",
                "近7天销量",
                "近30天销量",
                "保质期（天）",
                "标注到期日期",
            ],
        )

    def test_custom_inventory_unit_is_kept_for_analysis(self):
        inventory = template_frame("inventory", True).head(1)
        draft = inventory_editor_frame(inventory)
        draft.loc[0, "单位"] = "其他（手动填写）"
        draft.loc[0, "自定义单位"] = "礼盒"
        submitted = submitted_inventory(draft)
        self.assertEqual(submitted.iloc[0]["单位"], "礼盒")

    def test_blank_rows_with_unit_prompt_are_not_submitted(self):
        draft = inventory_editor_frame(blank_entry_frame(INVENTORY_COLUMNS, 3))
        self.assertTrue(submitted_inventory(draft).empty)

    def test_box_order_is_converted_to_inventory_unit(self):
        plan_input = pd.DataFrame(
            [["海盐薯片 60g", "6900000000012", 2, "箱", "", 24, "袋", "", "周末陈列"]],
            columns=DIRECT_PLAN_COLUMNS,
        )
        plan = submitted_plan(plan_input)
        self.assertEqual(plan.iloc[0]["计划进货数量"], 48)
        self.assertEqual(plan.iloc[0]["单位"], "袋")
        self.assertEqual(plan.iloc[0]["录入换算说明"], "2 箱 x 24 = 48 袋")

        result = analyse(template_frame("inventory", True), plan, date(2026, 5, 25))
        review = result.plan_review[result.plan_review["条码"] == "6900000000012"].iloc[0]
        self.assertEqual(review["进货后库存"], 51)
        self.assertEqual(review["录入换算说明"], "2 箱 x 24 = 48 袋")

    def test_cross_unit_order_without_factor_is_blocked(self):
        plan_input = pd.DataFrame(
            [["海盐薯片 60g", "6900000000012", 2, "箱", "", "", "袋", "", ""]],
            columns=DIRECT_PLAN_COLUMNS,
        )
        plan = submitted_plan(plan_input)
        result = analyse(template_frame("inventory", True), plan, date(2026, 5, 25))
        review = result.plan_review[result.plan_review["条码"] == "6900000000012"].iloc[0]
        self.assertIn("数据不足无法自查", review["风险类型"])


if __name__ == "__main__":
    unittest.main()
