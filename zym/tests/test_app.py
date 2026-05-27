import logging
import unittest

from streamlit.testing.v1 import AppTest

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
        self.assertEqual(len(app.dataframe[0].value), 50)
        self.assertEqual(
            list(app.dataframe[0].value.columns[:6]),
            ["商品名", "进货日期", "当前库存", "单位", "近7天销量", "近30天销量"],
        )

    def test_direct_entry_demo_files_show_expected_summary(self):
        app = authenticated_app()
        app.radio[0].set_value("数据录入").run(timeout=10)
        next(button for button in app.button if button.label == "演示填充").click().run(timeout=10)
        next(button for button in app.button if button.label == "提交并查看提醒").click().run(timeout=10)
        app.radio[0].set_value("今日重点提醒").run(timeout=10)

        self.assertEqual(len(app.exception), 0)
        markup = "\n".join(element.value for element in app.markdown)
        self.assertIn('<div class="metric-grid">', markup)
        self.assertIn('<div class="risk-value">2</div>', markup)
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
        app.radio[0].set_value("今日重点提醒").run(timeout=10)

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


if __name__ == "__main__":
    unittest.main()
