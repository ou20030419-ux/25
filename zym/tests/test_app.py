import logging
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.history import PRODUCT_SHEET, SUMMARY_SHEET, history_product_segments
from src.io import template_bytes


logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(logging.ERROR)


def authenticated_app() -> AppTest:
    app = AppTest.from_file("app.py")
    app.secrets["APP_PASSWORD"] = "test-password"
    app.session_state["app_password_ok"] = True
    return app.run(timeout=10)


class AppFlowTests(unittest.TestCase):
    def test_direct_entry_starts_with_fifty_inventory_rows(self):
        app = authenticated_app()
        app.radio[0].set_value("数据录入").run(timeout=10)
        inventory_sections = [frame.value for frame in app.dataframe[:2]]
        self.assertEqual(len(inventory_sections), 2)
        self.assertTrue(all(len(frame) == 10 for frame in inventory_sections))
        self.assertEqual(
            list(inventory_sections[0].columns),
            ["序号", "商品名", "上次进货总量", "本进货周期销量", "库存剩余量", "单位", "近30天销量"],
        )
        self.assertEqual(
            list(inventory_sections[1].columns),
            ["序号", "商品名", "进货日期", "保质期（天）", "标注到期日期", "货架位置", "仓库位置", "品类"],
        )
        markdown = "\n".join(element.value for element in app.markdown)
        self.assertIn("当前已填写 0 行", markdown)
        self.assertNotIn("基本不需要横向滑动", markdown)

    def test_direct_entry_demo_files_show_expected_summary(self):
        app = authenticated_app()
        app.radio[0].set_value("数据录入").run(timeout=10)
        next(button for button in app.button if button.label == "演示填充").click().run(timeout=10)
        next(button for button in app.button if button.label == "提交并查看提醒").click().run(timeout=10)
        app.radio[0].set_value("本次重点提醒").run(timeout=10)

        self.assertEqual(len(app.exception), 0)
        markup = "\n".join(element.value for element in app.markdown)
        self.assertIn('<div class="metric-grid">', markup)
        self.assertIn('<div class="risk-value">3</div>', markup)
        self.assertIn("海盐薯片 60g", markup)
        self.assertIn("坚果能量棒", markup)
        self.assertIn("演示数据", markup)

    def test_expiry_service_page_shows_estimated_expiry_source(self):
        app = authenticated_app()
        app.radio[0].set_value("数据录入").run(timeout=10)
        next(button for button in app.button if button.label == "演示填充").click().run(timeout=10)
        next(button for button in app.button if button.label == "提交并查看提醒").click().run(timeout=10)
        app.radio[0].set_value("临期与过期提示").run(timeout=10)

        self.assertEqual(len(app.exception), 0)
        markup = "\n".join(element.value for element in app.markdown)
        self.assertIn("临期与过期提示", markup)
        self.assertIn("7天内临期", markup)
        details = "\n".join(
            frame.value.to_string() for frame in app.dataframe if not frame.value.empty
        )
        self.assertIn("按进货日期及保质期估算", details)

    def test_uploaded_demo_files_show_expected_summary(self):
        app = authenticated_app()
        app.radio[0].set_value("数据录入").run(timeout=10)
        app.radio[1].set_value("上传表格").run(timeout=10)
        app.file_uploader[0].upload("库存演示.xlsx", template_bytes("inventory", True))
        app.file_uploader[1].upload("进货演示.xlsx", template_bytes("plan", True))
        app.run(timeout=10)
        app.radio[0].set_value("本次重点提醒").run(timeout=10)

        self.assertEqual(len(app.exception), 0)
        markup = "\n".join(element.value for element in app.markdown)
        self.assertIn("快缺货", markup)
        self.assertIn("海盐薯片 60g", markup)

    def test_rules_page_explains_non_automatic_decision_scope(self):
        app = authenticated_app()
        app.radio[0].set_value("规则说明").run(timeout=10)
        markdown = "\n".join(element.value for element in app.markdown)
        subheaders = [element.value for element in app.subheader]
        self.assertIn("为什么不自动给出补货量", subheaders)
        self.assertIn("MVP_RULESET_V2", markdown)

    def test_home_page_shows_public_mobile_summary(self):
        app = authenticated_app()
        markup = "\n".join(element.value for element in app.markdown)
        self.assertIn("首页总览", markup)
        self.assertIn("公网版本仅用于演示", markup)
        self.assertIn("本周期工作台", markup)
        self.assertIn("30天历史归档", markup)

    def test_history_archive_saves_current_analysis(self):
        app = authenticated_app()
        app.radio[0].set_value("数据录入").run(timeout=10)
        next(button for button in app.button if button.label == "演示填充").click().run(timeout=10)
        next(button for button in app.button if button.label == "提交并查看提醒").click().run(timeout=10)
        app.radio[0].set_value("30天历史归档").run(timeout=10)
        next(button for button in app.button if button.label == "保存本次到30天归档").click().run(timeout=10)

        self.assertEqual(len(app.exception), 0)
        history = app.session_state["history_archive"]
        self.assertEqual(len(history[SUMMARY_SHEET]), 1)
        self.assertIn("快缺货", history[SUMMARY_SHEET].columns)

    def test_history_segments_classify_hot_and_slow_products(self):
        history = {
            PRODUCT_SHEET: pd.DataFrame(
                [
                    {
                        "归档日期": "2026-06-01",
                        "商品键": "hot",
                        "商品名": "海盐薯片",
                        "品类": "膨化",
                        "上次进货总量": 24,
                        "库存剩余量": 3,
                        "本进货周期销量": 21,
                        "预计可售进货周期数": 0.1,
                        "风险类型": "快缺货",
                    },
                    {
                        "归档日期": "2026-06-08",
                        "商品键": "hot",
                        "商品名": "海盐薯片",
                        "品类": "膨化",
                        "上次进货总量": 24,
                        "库存剩余量": 2,
                        "本进货周期销量": 22,
                        "预计可售进货周期数": 0.1,
                        "风险类型": "快缺货",
                    },
                    {
                        "归档日期": "2026-06-01",
                        "商品键": "slow",
                        "商品名": "芒果软糖",
                        "品类": "糖果",
                        "上次进货总量": 20,
                        "库存剩余量": 20,
                        "本进货周期销量": 0,
                        "风险类型": "疑似滞销",
                    },
                    {
                        "归档日期": "2026-06-08",
                        "商品键": "slow",
                        "商品名": "芒果软糖",
                        "品类": "糖果",
                        "上次进货总量": 20,
                        "库存剩余量": 20,
                        "本进货周期销量": 0,
                        "风险类型": "疑似滞销",
                    },
                ]
            )
        }

        segments = history_product_segments(history)
        by_name = segments.set_index("商品名")

        self.assertEqual(by_name.loc["海盐薯片", "经营分层"], "稳定好卖")
        self.assertEqual(by_name.loc["芒果软糖", "经营分层"], "持续滞销")
        self.assertIn("现有库存", by_name.loc["海盐薯片", "建议动作"])


if __name__ == "__main__":
    unittest.main()
