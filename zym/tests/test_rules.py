import unittest
from datetime import date

import pandas as pd

from src.io import template_frame
from src.rules import analyse


def labelled_inventory(rows: list[list[object]]) -> pd.DataFrame:
    records = []
    for name, barcode, category, _batch, stock, sales_7, sales_30, expiry, shelf, unit in rows:
        records.append(
            {
                "商品名": name,
                "进货日期": "",
                "当前库存": stock,
                "单位": unit,
                "近7天销量": sales_7,
                "近30天销量": sales_30,
                "保质期（天）": "",
                "标注到期日期": expiry,
                "货架位置": shelf,
                "条码": barcode,
                "品类": category,
            }
        )
    return pd.DataFrame(records, columns=template_frame("inventory").columns)


class RiskRulesTests(unittest.TestCase):
    def test_sample_data_covers_core_workflow(self):
        result = analyse(template_frame("inventory", True), template_frame("plan", True), date(2026, 5, 25))
        self.assertEqual(result.counts["快缺货"], 2)
        self.assertEqual(result.counts["库存偏高"], 1)
        self.assertEqual(result.counts["疑似滞销"], 1)
        self.assertEqual(result.counts["临期"], 1)
        self.assertEqual(result.counts["进货风险"], 3)
        self.assertEqual(result.counts["可能漏订"], 1)
        cake_expiry = result.expiry_batches[result.expiry_batches["商品名"] == "酸奶小蛋糕"]
        self.assertEqual(set(cake_expiry["临期类型"]), {"7天内临期", "8至30天临期"})
        self.assertEqual(result.missed_orders.iloc[0]["商品名"], "坚果能量棒")

    def test_inventory_only_disables_plan_outputs(self):
        result = analyse(template_frame("inventory", True), None, date(2026, 5, 25))
        self.assertFalse(result.plan_uploaded)
        self.assertTrue(result.plan_review.empty)
        self.assertTrue(result.missed_orders.empty)

    def test_batch_sales_conflict_blocks_stock_risk(self):
        inventory = labelled_inventory(
            [
                ["短保糕点", "001", "糕点", "A", 1, 14, 30, "2026-08-01", "A1", "个"],
                ["短保糕点", "001", "糕点", "B", 1, 21, 30, "2026-08-01", "A1", "个"],
            ]
        )
        result = analyse(inventory, None, date(2026, 5, 25))
        self.assertEqual(result.counts["快缺货"], 0)
        self.assertIn("销量冲突", set(result.quality_issues["问题类型"]))
        self.assertIn("近7天销量待核对", result.products.iloc[0]["数据状态"])

    def test_barcode_identity_conflict_is_not_analyzed(self):
        inventory = labelled_inventory(
            [
                ["薯片", "001", "膨化", "A", 1, 14, 30, "2026-12-01", "A1", "袋"],
                ["饼干", "001", "饼干", "B", 1, 14, 30, "2026-12-01", "B1", "袋"],
            ]
        )
        result = analyse(inventory, None, date(2026, 5, 25))
        self.assertEqual(result.counts["快缺货"], 0)
        self.assertIn("条码身份冲突", set(result.quality_issues["问题类型"]))

    def test_expiry_boundary_categories(self):
        inventory = labelled_inventory(
            [
                ["当天", "1", "糕点", "A", 1, 7, 7, "2026-05-25", "A", "个"],
                ["七天", "2", "糕点", "A", 1, 7, 7, "2026-06-01", "A", "个"],
                ["八天", "3", "糕点", "A", 1, 7, 7, "2026-06-02", "A", "个"],
                ["三十天", "4", "糕点", "A", 1, 7, 7, "2026-06-24", "A", "个"],
                ["三十一天", "5", "糕点", "A", 1, 7, 7, "2026-06-25", "A", "个"],
            ]
        )
        result = analyse(inventory, None, date(2026, 5, 25))
        categories = dict(zip(result.expiry_batches["商品名"], result.expiry_batches["临期类型"]))
        self.assertEqual(categories["当天"], "已到期")
        self.assertEqual(categories["七天"], "7天内临期")
        self.assertEqual(categories["八天"], "8至30天临期")
        self.assertEqual(categories["三十天"], "8至30天临期")
        self.assertNotIn("三十一天", categories)

    def test_purchase_date_and_shelf_life_estimate_expiry(self):
        inventory = pd.DataFrame(
            [
                {
                    "商品名": "鲜奶",
                    "进货日期": "2026-05-20",
                    "当前库存": 6,
                    "单位": "瓶",
                    "近7天销量": 4,
                    "近30天销量": 16,
                    "保质期（天）": 7,
                    "标注到期日期": "",
                    "货架位置": "冷藏-01",
                    "条码": "milk-01",
                    "品类": "乳品",
                }
            ],
            columns=template_frame("inventory").columns,
        )
        result = analyse(inventory, None, date(2026, 5, 25))
        expiry = result.expiry_batches.iloc[0]
        self.assertEqual(expiry["临期类型"], "7天内临期")
        self.assertEqual(expiry["到期日来源"], "按进货日期及保质期估算")
        self.assertEqual(expiry["距到期天数"], 2)

    def test_legacy_expiry_date_column_still_drives_expiry_warning(self):
        legacy = pd.DataFrame(
            [["酸奶", "001", "乳品", "OLD", 2, 3, 10, "2026-05-27", "冷藏-01", "杯"]],
            columns=["商品名", "条码", "品类", "批次号", "当前库存", "近7天销量", "近30天销量", "到期日期", "货架位置", "单位"],
        )
        result = analyse(legacy, None, date(2026, 5, 25))
        self.assertEqual(result.counts["临期"], 1)
        self.assertEqual(result.expiry_batches.iloc[0]["到期日来源"], "包装标注到期日")

    def test_wrong_plan_barcode_does_not_fallback_to_name(self):
        inventory = labelled_inventory(
            [["薯片", "001", "膨化", "A", 1, 14, 20, "2026-12-01", "A1", "袋"]]
        )
        plan = pd.DataFrame(
            [["薯片", "999", 20, "袋", ""]],
            columns=template_frame("plan").columns,
        )
        result = analyse(inventory, plan, date(2026, 5, 25))
        self.assertEqual(result.plan_review.iloc[0]["匹配状态"], "条码未匹配库存商品")
        self.assertEqual(result.missed_orders.iloc[0]["判断状态"], "可能漏订")

    def test_negative_plan_quantity_makes_missed_order_uncertain(self):
        inventory = labelled_inventory(
            [["薯片", "001", "膨化", "A", 1, 14, 20, "2026-12-01", "A1", "袋"]]
        )
        plan = pd.DataFrame(
            [["薯片", "001", -2, "袋", ""]],
            columns=template_frame("plan").columns,
        )
        result = analyse(inventory, plan, date(2026, 5, 25))
        self.assertEqual(result.missed_orders.iloc[0]["判断状态"], "待核对是否漏订")

    def test_mixed_plan_unit_blocks_quantity_conclusion(self):
        inventory = labelled_inventory(
            [["薯片", "001", "膨化", "A", 1, 14, 20, "2026-12-01", "A1", "袋"]]
        )
        plan = pd.DataFrame(
            [["薯片", "001", 2, "箱", ""]],
            columns=template_frame("plan").columns,
        )
        result = analyse(inventory, plan, date(2026, 5, 25))
        self.assertIn("数据不足无法自查", result.plan_review.iloc[0]["风险类型"])
        self.assertEqual(result.missed_orders.iloc[0]["判断状态"], "待核对是否漏订")
        self.assertIn("单位不一致", set(result.quality_issues["问题类型"]))

    def test_missing_required_field_is_reported_without_crashing(self):
        inventory = pd.DataFrame(
            [["薯片", "001", 2]],
            columns=["商品名", "条码", "当前库存"],
        )
        result = analyse(inventory, None, date(2026, 5, 25))
        self.assertEqual(result.counts["快缺货"], 0)
        self.assertIn("缺失字段", set(result.quality_issues["问题类型"]))

    def test_name_only_plan_is_blocked_when_name_maps_to_two_barcodes(self):
        inventory = labelled_inventory(
            [
                ["饮料", "001", "饮料", "A", 1, 14, 30, "2026-12-01", "A1", "瓶"],
                ["饮料", "002", "饮料", "A", 1, 14, 30, "2026-12-01", "A2", "瓶"],
            ]
        )
        plan = pd.DataFrame(
            [["饮料", "", 10, "瓶", ""]],
            columns=template_frame("plan").columns,
        )
        result = analyse(inventory, plan, date(2026, 5, 25))
        self.assertEqual(result.plan_review.iloc[0]["匹配状态"], "名称匹配歧义")
        self.assertEqual(set(result.missed_orders["判断状态"]), {"待核对是否漏订"})

    def test_invalid_stock_in_one_batch_blocks_product_stock_risk(self):
        inventory = labelled_inventory(
            [
                ["糕点", "001", "糕点", "A", 1, 14, 30, "2026-12-01", "A1", "个"],
                ["糕点", "001", "糕点", "B", "待盘点", 14, 30, "2026-12-01", "A1", "个"],
            ]
        )
        result = analyse(inventory, None, date(2026, 5, 25))
        self.assertEqual(result.counts["快缺货"], 0)
        self.assertIn("库存待核对", result.products.iloc[0]["数据状态"])

    def test_missing_inventory_unit_blocks_quantity_conclusion(self):
        inventory = labelled_inventory(
            [["薯片", "001", "膨化", "A", 1, 14, 20, "2026-12-01", "A1", ""]]
        )
        result = analyse(inventory, None, date(2026, 5, 25))
        self.assertEqual(result.counts["快缺货"], 0)
        self.assertIn("单位缺失", set(result.quality_issues["问题类型"]))


if __name__ == "__main__":
    unittest.main()
