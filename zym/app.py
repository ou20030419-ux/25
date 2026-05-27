from __future__ import annotations

from datetime import datetime
from html import escape

import pandas as pd
import streamlit as st

from src.config import INVENTORY_COLUMNS, RULESET_VERSION, STORE_TIMEZONE
from src.entry import (
    DIRECT_PLAN_COLUMNS,
    UNIT_OPTIONS,
    blank_entry_frame,
    inventory_editor_frame,
    plan_editor_frame,
    submitted_inventory,
    submitted_plan,
)
from src.export import build_export_workbook
from src.io import InputReadError, read_table, template_bytes, template_frame
from src.rules import AnalysisResult, analyse


st.set_page_config(
    page_title="零食门店商品动销与批次临期管理助手",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="auto",
)

st.markdown(
    """
    <style>
    :root {
        --app-green: #139568;
        --app-green-dark: #0b7350;
        --app-green-soft: #e8f5ef;
        --app-text: #182339;
        --app-muted: #667085;
        --app-border: #e2e8e5;
        --app-surface: #ffffff;
        --app-bg: #fafcfb;
        --risk-red: #ef4c3e;
        --risk-blue: #2362a3;
        --risk-amber: #de7c19;
    }
    .stApp {background: var(--app-bg);}
    [data-testid="stAppDeployButton"] {display:none;}
    .block-container {padding-top: 2.1rem; padding-bottom: 2.5rem; max-width: 1180px;}
    h1, h2, h3 {color: var(--app-text); letter-spacing: 0;}
    h1 {font-size: 2.15rem !important; font-weight: 760 !important; margin-bottom: .25rem !important;}
    h2 {font-size: 1.75rem !important; font-weight: 740 !important;}
    h3 {font-size: 1.18rem !important;}
    p, label {color: var(--app-text);}
    .app-subtitle {color: var(--app-muted); margin: -.1rem 0 1.35rem; font-size: .96rem;}
    .section-lead {color: var(--app-muted); margin-top: -.65rem; margin-bottom: 1.2rem;}
    .source-badge {
        display: inline-flex; align-items: center; gap: .25rem; padding: .25rem .65rem;
        margin-left: .55rem; font-size: .82rem; font-weight: 600; color: var(--app-green-dark);
        border: 1px solid #a8dfc9; border-radius: 6px; background: #f0fbf6; vertical-align: middle;
    }
    [data-testid="stSidebar"] {
        background: #fff; border-right: 1px solid var(--app-border);
    }
    [data-testid="stSidebar"] > div:first-child {padding-top: 1.2rem;}
    .sidebar-brand {
        display:flex; align-items:center; gap:.7rem; font-weight:760; font-size:1.08rem;
        line-height:1.45; color:var(--app-text); margin:.2rem 0 1.35rem;
    }
    .brand-mark {
        width:40px; height:40px; display:grid; place-items:center; border-radius:8px;
        color:#fff; background:var(--app-green); font-size:22px;
    }
    .mobile-brand {display:none;}
    [data-testid="stSidebar"] [role="radiogroup"] label {
        border-radius: 8px; padding: .58rem .55rem; margin: .12rem 0;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label > div:first-child {display:none;}
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
        color: var(--app-green-dark); background: var(--app-green-soft); font-weight: 650;
    }
    .sidebar-note {
        margin-top: 1rem; border:1px solid var(--app-border); border-radius:8px;
        padding:.72rem; color:var(--app-muted); font-size:.84rem; background:#fbfcfb;
    }
    .entry-callout {
        border:1px solid #a8dfc9; border-radius:8px; background:#f1fbf6;
        color:var(--app-green-dark); padding:.72rem .82rem; margin:.35rem 0 1rem;
        font-size:.92rem; line-height:1.6;
    }
    .sidebar-note strong {display:block; color:var(--app-text); margin-bottom:.2rem;}
    .metric-grid {
        display:grid; grid-template-columns:repeat(6, minmax(0, 1fr)); gap:16px;
        margin:1.05rem 0 1.75rem;
    }
    .metric-grid.expiry-grid {grid-template-columns:repeat(3, minmax(0, 1fr));}
    .risk-card {
        border:1px solid var(--app-border); border-radius:8px; min-height:126px;
        padding:1rem .85rem .8rem; background:var(--app-surface);
        display:flex; flex-direction:column; justify-content:space-between;
    }
    .home-grid, .priority-grid {
        display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:14px;
        margin:1rem 0 1.45rem;
    }
    .home-card, .priority-card, .auth-card {
        border:1px solid var(--app-border); border-radius:10px; background:#fff;
        padding:1rem; box-shadow:0 10px 28px rgba(24,35,57,.045);
    }
    .home-card strong, .priority-card strong {display:block; color:var(--app-text); margin-bottom:.36rem;}
    .home-card span, .priority-card span {color:var(--app-muted); font-size:.9rem; line-height:1.55;}
    .priority-card.urgent {border-color:#f5b7b1; background:#fff8f7;}
    .priority-card.expiry {border-color:#f4cf9e; background:#fffaf3;}
    .priority-card.review {border-color:#bbd3ed; background:#f6fbff;}
    .priority-card.safe {border-color:#bedfd3; background:#f6fbf8;}
    .priority-type {font-size:.78rem; font-weight:700; color:var(--app-green-dark); margin-bottom:.4rem;}
    .public-warning {
        border:1px solid #ffd6a8; border-radius:8px; background:#fff8ec;
        color:#8a4a08; padding:.78rem .88rem; margin:.7rem 0 1rem; line-height:1.55;
    }
    .auth-card {max-width:460px; margin:3.5rem auto 1rem;}
    .risk-card.urgent {border-color:#f5b7b1; color:var(--risk-red);}
    .risk-card.safe {border-color:#bedfd3; color:var(--app-green-dark);}
    .risk-card.review {border-color:#bbd3ed; color:var(--risk-blue);}
    .risk-card.expiry {border-color:#f4cf9e; color:var(--risk-amber);}
    .risk-name {font-size:.94rem; font-weight:600; color:var(--app-text); white-space:nowrap;}
    .risk-card .risk-value {font-size:2.15rem; line-height:1; font-weight:720; color:inherit;}
    .evidence-table {
        width:100%; border-collapse:separate; border-spacing:0; border:1px solid var(--app-border);
        border-radius:8px; overflow:hidden; background:#fff; margin-top:.7rem;
    }
    .evidence-table th {
        text-align:left; padding:.7rem .72rem; font-size:.84rem; font-weight:500;
        color:var(--app-muted); background:#f8faf9; border-bottom:1px solid var(--app-border);
    }
    .evidence-table td {
        padding:.68rem .72rem; font-size:.9rem; color:var(--app-text);
        border-bottom:1px solid #edf1ef; vertical-align:top;
    }
    .evidence-table tr:last-child td {border-bottom:0;}
    .risk-pill {
        display:inline-block; border-radius:5px; padding:.18rem .38rem;
        font-size:.8rem; font-weight:600; color:var(--app-green-dark); background:var(--app-green-soft);
    }
    .risk-pill.urgent {color:#d63429;background:#ffebe8;}
    .risk-pill.review {color:#1d5b94;background:#e9f2fb;}
    .risk-pill.expiry {color:#bd6813;background:#fff1df;}
    div.stButton > button[kind="primary"], div.stDownloadButton > button[kind="primary"] {
        border-radius:7px; background:var(--app-green); border-color:var(--app-green);
        min-height:2.8rem; font-weight:650;
    }
    div.stButton > button[kind="primary"]:hover, div.stDownloadButton > button[kind="primary"]:hover {
        background:var(--app-green-dark); border-color:var(--app-green-dark);
    }
    div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {
        border-radius:8px; overflow:hidden;
    }
    [data-testid="stAlert"] {border-radius:8px;}
    @media (max-width: 1100px) {
        .metric-grid {grid-template-columns:repeat(3, minmax(0, 1fr));}
    }
    @media (max-width: 768px) {
        .block-container {padding:1.15rem .95rem 5rem;}
        h1 {font-size:1.24rem !important;}
        h2 {font-size:1.2rem !important;}
        .mobile-brand {
            display:flex; align-items:center; gap:.42rem; color:var(--app-text);
            font-size:1rem; font-weight:700; margin-top:2.35rem; margin-bottom:1rem;
        }
        .mobile-brand .brand-mark {width:29px; height:29px; font-size:16px;}
        .app-subtitle {display:none;}
        .metric-grid {grid-template-columns:repeat(2, minmax(0, 1fr)); gap:9px;}
        .metric-grid.expiry-grid {grid-template-columns:repeat(2, minmax(0, 1fr));}
        .home-grid, .priority-grid {grid-template-columns:1fr; gap:10px;}
        .home-card, .priority-card {padding:.86rem .78rem;}
        .risk-card {min-height:98px; padding:.68rem .6rem;}
        .risk-name {font-size:.83rem;}
        .risk-card .risk-value {font-size:1.75rem;}
        .evidence-table {display:block; overflow-x:auto; white-space:nowrap;}
        [data-testid="stHorizontalBlock"] {gap:.45rem;}
        button {min-height:2.6rem;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_configured_password() -> str | None:
    try:
        password = st.secrets["APP_PASSWORD"]
    except Exception:
        return None
    password_text = str(password).strip()
    return password_text or None


def require_password() -> None:
    expected_password = get_configured_password()
    if not expected_password:
        st.error("请先配置 APP_PASSWORD")
        st.info("在 Streamlit Community Cloud 的 Secrets 中添加：APP_PASSWORD = \"你的访问密码\"")
        st.stop()
    if st.session_state.get("app_password_ok"):
        return
    st.markdown(
        """
        <div class="auth-card">
            <h2>零食门店商品动销与批次临期管理助手</h2>
            <p class="section-lead">请输入访问密码后继续使用。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("password_form"):
        entered_password = st.text_input("访问密码", type="password")
        submitted = st.form_submit_button("进入系统", type="primary")
    if submitted:
        if entered_password == expected_password:
            st.session_state["app_password_ok"] = True
            st.rerun()
        st.error("密码不正确，请重试。")
    st.stop()


@st.cache_data(show_spinner=False)
def load_uploaded(content: bytes, filename: str) -> pd.DataFrame:
    return read_table(content, filename)


def page_intro(title: str, description: str = "", badge: str = "") -> None:
    badge_html = f'<span class="source-badge">{escape(badge)}</span>' if badge else ""
    st.markdown(f"<h2>{escape(title)}{badge_html}</h2>", unsafe_allow_html=True)
    if description:
        st.markdown(f'<p class="section-lead">{escape(description)}</p>', unsafe_allow_html=True)


def shown(frame: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=columns or [])
    data = frame.drop(
        columns=[column for column in frame.columns if str(column).startswith("_")],
        errors="ignore",
    ).copy()
    if columns:
        for column in columns:
            if column not in data.columns:
                data[column] = pd.NA
        data = data[columns]
    for column in data.columns:
        if data[column].dtype == object:
            data[column] = data[column].map(
                lambda value: "" if pd.isna(value) else str(value)
            )
    return data


def message_without_plan() -> None:
    st.info("尚未提供计划进货信息。直接填写或上传进货单后，可分析进货风险和可能漏订商品。")


def metric_cards_html(counts: dict[str, int]) -> str:
    card_styles = {
        "快缺货": "urgent",
        "库存偏高": "safe",
        "疑似滞销": "review",
        "临期": "expiry",
        "进货风险": "urgent",
        "可能漏订": "safe",
    }
    labels = ["快缺货", "库存偏高", "疑似滞销", "临期", "进货风险", "可能漏订"]
    cards = "".join(
        f'<div class="risk-card {card_styles[label]}"><div class="risk-name">{escape(label)}</div>'
        f'<div class="risk-value">{counts.get(label, 0)}</div></div>'
        for label in labels
    )
    return f'<div class="metric-grid">{cards}</div>'


def format_quantity(value: object) -> str:
    if pd.isna(value):
        return ""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def priority_items(result: AnalysisResult, limit: int = 6) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if not result.expiry_batches.empty:
        for _, row in result.expiry_batches.head(limit).iterrows():
            qty = format_quantity(row.get("批次库存"))
            detail = (
                f'{row.get("临期类型", "")}，库存 {qty}{row.get("单位", "")}；'
                f'到期 {row.get("到期日期", "")}，位置 {row.get("货架位置", "")}'
            )
            items.append(
                {
                    "type": "临期处理",
                    "title": str(row.get("商品名", "")),
                    "detail": detail,
                    "tone": "expiry" if row.get("临期类型") != "已到期" else "urgent",
                }
            )
    if not result.anomalies.empty:
        non_expiry = result.anomalies[
            ~result.anomalies["风险类型"].fillna("").str.contains("临期风险")
        ]
        for _, row in non_expiry.head(limit).iterrows():
            items.append(
                {
                    "type": str(row.get("风险类型", "库存提醒")),
                    "title": str(row.get("商品名", "")),
                    "detail": str(row.get("提示依据", "")),
                    "tone": "urgent" if "快缺货" in str(row.get("风险类型", "")) else "review",
                }
            )
    if result.plan_uploaded and not result.plan_review.empty:
        risky_plan = result.plan_review[result.plan_review["风险类型"].fillna("") != ""]
        for _, row in risky_plan.head(limit).iterrows():
            items.append(
                {
                    "type": "进货复核",
                    "title": str(row.get("商品名", "")),
                    "detail": str(row.get("提示依据", "")),
                    "tone": "urgent",
                }
            )
    if result.plan_uploaded and not result.missed_orders.empty:
        missed = result.missed_orders[result.missed_orders["判断状态"] == "可能漏订"]
        for _, row in missed.head(limit).iterrows():
            items.append(
                {
                    "type": "可能漏订",
                    "title": str(row.get("商品名", "")),
                    "detail": str(row.get("提示依据", "")),
                    "tone": "safe",
                }
            )
    return items[:limit]


def render_priority_cards(result: AnalysisResult) -> None:
    items = priority_items(result)
    if not items:
        st.success("暂未发现需要优先处理的商品。")
        return
    cards = "".join(
        f'<div class="priority-card {escape(item["tone"])}">'
        f'<div class="priority-type">{escape(item["type"])}</div>'
        f'<strong>{escape(item["title"])}</strong>'
        f'<span>{escape(item["detail"])}</span>'
        "</div>"
        for item in items
    )
    st.markdown(f'<div class="priority-grid">{cards}</div>', unsafe_allow_html=True)


def render_home(result: AnalysisResult | None, analysis_source: str) -> None:
    page_intro(
        "首页总览",
        "零食门店商品动销与批次临期管理助手，适合手机快速查看今日优先事项。",
    )
    st.markdown(
        '<div class="public-warning">公网版本仅用于演示、培训或低敏数据自查；不建议上传真实门店敏感数据、'
        "客户信息、完整供应链价格或内部考核资料。</div>",
        unsafe_allow_html=True,
    )
    if result is None:
        cards = [
            ("录入或上传", "填写库存、销量、进货日期、保质期，也可上传整理好的表格。"),
            ("自动提示", "识别快缺货、高库存、滞销、临期、进货风险和可能漏订。"),
            ("导出留档", "分析完成后可导出 Excel，用于复核、沟通和归档。"),
        ]
        html = "".join(
            f"<div class='home-card'><strong>{escape(title)}</strong><span>{escape(body)}</span></div>"
            for title, body in cards
        )
        st.markdown(f'<div class="home-grid">{html}</div>', unsafe_allow_html=True)
        st.info("请先进入“数据录入”填写或上传库存销售信息。")
        return

    if analysis_source:
        st.caption(f"当前数据来源：{analysis_source}")
    st.markdown(metric_cards_html(result.counts), unsafe_allow_html=True)
    st.subheader("今日重点处理清单")
    render_priority_cards(result)
    with st.expander("展开查看详细表格"):
        st.markdown("**库存与临期异常**")
        st.dataframe(shown(result.anomalies), width="stretch", hide_index=True)
        if not result.expiry_batches.empty:
            st.markdown("**临期批次明细**")
            st.dataframe(shown(result.expiry_batches), width="stretch", hide_index=True)
        if result.plan_uploaded:
            st.markdown("**进货单自查与可能漏订**")
            st.dataframe(shown(result.plan_review), width="stretch", hide_index=True)
            st.dataframe(shown(result.missed_orders), width="stretch", hide_index=True)


def initialise_direct_entry() -> None:
    defaults = {
        "direct_inventory_draft": inventory_editor_frame(blank_entry_frame(INVENTORY_COLUMNS, 50)),
        "direct_plan_draft": blank_entry_frame(DIRECT_PLAN_COLUMNS, 20),
        "direct_inventory_submitted": None,
        "direct_plan_submitted": None,
        "direct_include_plan": False,
        "direct_data_origin": "页面直接填写",
        "direct_editor_revision": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    st.session_state["direct_inventory_draft"] = inventory_editor_frame(
        st.session_state["direct_inventory_draft"]
    )
    st.session_state["direct_plan_draft"] = plan_editor_frame(
        st.session_state["direct_plan_draft"]
    )
    inventory_missing_rows = 50 - len(st.session_state["direct_inventory_draft"])
    if inventory_missing_rows > 0:
        st.session_state["direct_inventory_draft"] = pd.concat(
            [
                st.session_state["direct_inventory_draft"],
                inventory_editor_frame(blank_entry_frame(INVENTORY_COLUMNS, inventory_missing_rows)),
            ],
            ignore_index=True,
        )
    plan_missing_rows = 20 - len(st.session_state["direct_plan_draft"])
    if plan_missing_rows > 0:
        st.session_state["direct_plan_draft"] = pd.concat(
            [
                st.session_state["direct_plan_draft"],
                blank_entry_frame(DIRECT_PLAN_COLUMNS, plan_missing_rows),
            ],
            ignore_index=True,
        )


def render_templates() -> None:
    st.subheader("模板与演示数据")
    st.caption("批量填写可下载 Excel 模板；模板包含进货日期、保质期与可选标注到期日，条码保留为文本。")
    col1, col2, col3, col4 = st.columns(4)
    col1.download_button(
        "库存表空白模板",
        template_bytes("inventory"),
        "库存销售表_空白模板.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
    col2.download_button(
        "进货单空白模板",
        template_bytes("plan"),
        "计划进货单_空白模板.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
    col3.download_button(
        "库存表演示数据",
        template_bytes("inventory", sample=True),
        "库存销售表_演示数据.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
    col4.download_button(
        "进货单演示数据",
        template_bytes("plan", sample=True),
        "计划进货单_演示数据.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )


def render_file_upload(
    inventory_upload: st.runtime.uploaded_file_manager.UploadedFile | None,
    plan_upload: st.runtime.uploaded_file_manager.UploadedFile | None,
    result: AnalysisResult | None,
) -> None:
    st.subheader("上传已整理的表格")
    st.write("适合已有库存表或一次录入商品较多的情况。")
    if result is None:
        st.info("请先在左侧上传库存销售表。计划进货单可稍后补充。")
    else:
        left, right = st.columns(2)
        with left:
            st.success(f"库存销售表已载入：{inventory_upload.name}")
        with right:
            if plan_upload:
                st.success(f"计划进货单已载入：{plan_upload.name}")
            else:
                st.info("可只做库存风险自查，暂未上传进货单。")
    render_templates()


def render_direct_entry(result: AnalysisResult | None) -> None:
    st.subheader("直接录入商品库存、销量与保质信息")
    st.markdown(
        '<div class="entry-callout">先填商品名、进货日期、库存与销量，再填写保质期。'
        "系统会计算临期与过期提醒；包装上已有到期日时可直接标注。</div>",
        unsafe_allow_html=True,
    )
    action_left, action_right, _ = st.columns([1.5, 1.25, 2.25])
    if action_left.button("演示填充", width="stretch"):
        st.session_state["direct_inventory_draft"] = inventory_editor_frame(
            template_frame("inventory", True)
        )
        st.session_state["direct_plan_draft"] = plan_editor_frame(template_frame("plan", True))
        st.session_state["direct_include_plan"] = True
        st.session_state["direct_data_origin"] = "演示数据"
        st.session_state["direct_editor_revision"] += 1
        st.rerun()
    if action_right.button("清空", width="stretch"):
        st.session_state["direct_inventory_draft"] = inventory_editor_frame(
            blank_entry_frame(INVENTORY_COLUMNS, 50)
        )
        st.session_state["direct_plan_draft"] = blank_entry_frame(DIRECT_PLAN_COLUMNS, 20)
        st.session_state["direct_inventory_submitted"] = None
        st.session_state["direct_plan_submitted"] = None
        st.session_state["direct_include_plan"] = False
        st.session_state["direct_data_origin"] = "页面直接填写"
        st.session_state["direct_editor_revision"] += 1
        st.rerun()

    revision = st.session_state["direct_editor_revision"]
    submit_top = st.button("提交并查看提醒", type="primary", width="stretch", key="submit_entry_top")
    st.markdown("**商品清单与过期判断资料（最多 50 条）**")
    st.caption("库存数量后一栏即可选择库存/销售单位，例如填写 `12` 后选择 `瓶`；近7天与近30天销量采用同一单位。")
    inventory_draft = st.data_editor(
        st.session_state["direct_inventory_draft"],
        key=f"inventory_editor_{revision}",
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "商品名": st.column_config.TextColumn(help="可与条码任选其一填写；两者都有时优先使用条码"),
            "进货日期": st.column_config.TextColumn(help="建议格式：YYYY-MM-DD；用于无包装到期日时估算到期时间"),
            "当前库存": st.column_config.TextColumn(help="填写非负数量，例如 12"),
            "近7天销量": st.column_config.TextColumn(help="填写近 7 天售出的非负数量"),
            "近30天销量": st.column_config.TextColumn(help="填写近 30 天售出的非负数量"),
            "保质期（天）": st.column_config.TextColumn(help="填写正整数天数，例如 7、30、180"),
            "标注到期日期": st.column_config.TextColumn(
                "标注到期日期（可选）", help="包装有明确到期日期时填写，优先于系统估算；建议格式：YYYY-MM-DD"
            ),
            "货架位置": st.column_config.TextColumn(help="例如 A-01、冷藏柜-2，便于及时下架处理"),
            "条码": st.column_config.TextColumn(help="可留空；填写时请保留前导零"),
            "品类": st.column_config.TextColumn(help="例如饮料、乳制品、糕点，便于筛选"),
            "单位": st.column_config.SelectboxColumn(
                "库存/销量单位", options=UNIT_OPTIONS, help="数量分析均使用此基础单位"
            ),
            "自定义单位": st.column_config.TextColumn(
                help="选择“其他（手动填写）”时输入，例如毫升、礼盒"
            ),
        },
    )
    st.session_state["direct_inventory_draft"] = inventory_draft
    st.caption("临期计算：有标注到期日期时按标注判断；否则按 `进货日期 + 保质期（天）` 估算，并在结果中注明来源。")

    include_plan = st.checkbox("本次同时填写计划进货商品", key="direct_include_plan")
    plan_draft = st.session_state["direct_plan_draft"]
    if include_plan:
        st.markdown("**计划进货信息**")
        st.caption("可按箱、提等单位进货。若与库存单位不同，请填写换算数量，例如每箱折合 24 瓶。")
        plan_draft = st.data_editor(
            st.session_state["direct_plan_draft"],
            key=f"plan_editor_{revision}",
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "商品名": st.column_config.TextColumn(help="可与条码任选其一填写；两者都有时优先使用条码"),
                "条码": st.column_config.TextColumn(help="有条码时按条码匹配"),
                "进货单位": st.column_config.SelectboxColumn(options=UNIT_OPTIONS),
                "库存单位": st.column_config.SelectboxColumn(
                    options=UNIT_OPTIONS, help="应与上方该商品的库存/销量单位一致"
                ),
                "每进货单位折合库存单位数量": st.column_config.NumberColumn(
                    help="同一单位可填 1；例如 1 箱 = 24 瓶则填写 24",
                    min_value=0.01,
                ),
            },
        )
        st.session_state["direct_plan_draft"] = plan_draft

    st.caption("单位换算提示：例如 `1箱 = 24瓶`，跨单位进货需填写折合数量。")
    submit_bottom = st.button("提交并查看提醒", type="primary", width="stretch", key="submit_entry_bottom")
    if submit_top or submit_bottom:
        inventory = submitted_inventory(inventory_draft)
        if inventory.empty:
            st.warning("请至少填写一行库存销售信息后再分析。")
        else:
            st.session_state["direct_inventory_submitted"] = inventory
            st.session_state["direct_plan_submitted"] = submitted_plan(plan_draft) if include_plan else None
            st.rerun()

    if result is not None:
        st.success("已提交填写内容。可从左侧查看质量核对、提醒与导出结果；修改后请重新提交分析。")
    render_templates()


def render_entry(
    input_mode: str,
    inventory_upload: st.runtime.uploaded_file_manager.UploadedFile | None,
    plan_upload: st.runtime.uploaded_file_manager.UploadedFile | None,
    result: AnalysisResult | None,
) -> None:
    page_intro("数据录入", "系统只提供补货前复核提示，最终决定仍由员工结合现场情况作出。")
    if input_mode == "直接填写":
        render_direct_entry(result)
    else:
        render_file_upload(inventory_upload, plan_upload, result)


def render_quality(result: AnalysisResult) -> None:
    page_intro("数据质量核对", "先确认商品身份、数量和单位信息，再查看补货提示。")
    blocked_products = int((result.products["数据状态"] != "可分析").sum())
    blocking_issues = int((result.quality_issues["严重程度"] == "需先核对").sum()) if not result.quality_issues.empty else 0
    col1, col2, col3 = st.columns(3)
    col1.metric("可参与库存分析商品", int((result.products["数据状态"] == "可分析").sum()))
    col2.metric("待核对商品", blocked_products)
    col3.metric("需先核对问题", blocking_issues)
    if result.quality_issues.empty:
        st.success("未发现会影响本次分析的数据质量问题。")
    else:
        st.warning("存在数据质量提示。身份冲突、数量/销量或单位问题会阻断相关自动判断。")
        with st.expander("展开查看详细表格", expanded=False):
            st.dataframe(result.quality_issues, width="stretch", hide_index=True)


def render_summary(result: AnalysisResult, analysis_source: str) -> None:
    badge = "演示数据" if analysis_source == "演示数据" else ""
    page_intro("今日重点提醒", "根据当前规则计算，以下商品需要重点关注", badge)
    if analysis_source == "演示数据":
        st.caption("当前为演示数据，非真实结果。回到“数据录入”清空示例后可填写自己的商品。")
    else:
        st.caption(f"当前数据来源：{analysis_source}")
    if not result.quality_issues.empty:
        blocking = int((result.quality_issues["严重程度"] == "需先核对").sum())
        if blocking:
            st.warning(f"有 {blocking} 项数据需先核对；以下业务风险数字不包含被阻断的判断。")
    st.markdown(metric_cards_html(result.counts), unsafe_allow_html=True)
    if not result.plan_uploaded:
        message_without_plan()
    st.caption(f"当前规则版本：{RULESET_VERSION}。提醒仅用于复核，不代表必须采取某一进货决定。")
    st.subheader("今日重点处理清单")
    render_priority_cards(result)
    st.subheader("这些提醒来自哪些商品")
    explanation_rows: list[dict[str, str]] = []
    inventory_types = {
        "快缺货": "预计可售天数不超过 3 天",
        "库存偏高": "预计可售天数超过 30 天",
        "疑似滞销": "近7天无销量但仍有库存",
        "临期": "标注到期日或按进货日期与保质期估算后，存在已到期或 30 天内到期的库存",
    }
    for label, rule_text in inventory_types.items():
        source_label = "临期风险" if label == "临期" else label
        items = (
            result.anomalies[
                result.anomalies["风险类型"].fillna("").str.contains(source_label)
            ]["商品名"].dropna().drop_duplicates().tolist()
            if not result.anomalies.empty
            else []
        )
        explanation_rows.append(
            {
                "提醒类型": label,
                "商品数": str(result.counts[label]),
                "涉及商品": "、".join(items) or "无",
                "判断口径": rule_text,
            }
        )
    if result.plan_uploaded:
        plan_risky = (
            result.plan_review[
                result.plan_review["风险类型"].fillna("").str.contains(
                    "滞销或高库存仍进货|可能进货过量|临期库存仍进货"
                )
            ]["商品名"].dropna().drop_duplicates().tolist()
            if not result.plan_review.empty
            else []
        )
        missed_items = (
            result.missed_orders[result.missed_orders["判断状态"] == "可能漏订"][
                "商品名"
            ].dropna().drop_duplicates().tolist()
            if not result.missed_orders.empty
            else []
        )
        explanation_rows.extend(
            [
                {
                    "提醒类型": "进货风险",
                    "商品数": str(result.counts["进货风险"]),
                    "涉及商品": "、".join(plan_risky) or "无",
                    "判断口径": "高库存、滞销或临期商品仍计划进货，或进货后库存偏高",
                },
                {
                    "提醒类型": "可能漏订",
                    "商品数": str(result.counts["可能漏订"]),
                    "涉及商品": "、".join(missed_items) or "无",
                    "判断口径": "快缺货商品未匹配到正数计划进货量",
                },
            ]
        )
    pill_styles = {
        "快缺货": "urgent",
        "库存偏高": "",
        "疑似滞销": "review",
        "临期": "expiry",
        "进货风险": "urgent",
        "可能漏订": "",
    }
    body_rows = "".join(
        "<tr>"
        f'<td><span class="risk-pill {pill_styles.get(row["提醒类型"], "")}">{escape(row["提醒类型"])}</span></td>'
        f'<td>{escape(row["涉及商品"])}</td>'
        f'<td>{escape(row["判断口径"])}</td>'
        "</tr>"
        for row in explanation_rows
    )
    table_html = (
        '<table class="evidence-table"><thead><tr><th>提醒类型</th><th>商品名</th><th>说明</th></tr></thead>'
        f"<tbody>{body_rows}</tbody></table>"
    )
    with st.expander("展开查看提醒口径"):
        st.markdown(table_html, unsafe_allow_html=True)
    with st.expander("查看逐商品提示依据"):
        st.markdown("**库存与临期异常**")
        if result.anomalies.empty:
            st.write("无。")
        else:
            st.dataframe(
                shown(result.anomalies, ["商品名", "当前库存", "单位", "近7天销量", "预计可售天数", "风险类型", "提示依据"]),
                width="stretch",
                hide_index=True,
            )
        if result.plan_uploaded:
            st.markdown("**计划进货复核与可能漏订**")
            related_plan = result.plan_review[
                result.plan_review["风险类型"].fillna("") != ""
            ] if not result.plan_review.empty else pd.DataFrame()
            if not related_plan.empty:
                st.dataframe(
                    shown(related_plan, ["商品名", "计划进货数量", "进货后库存", "进货后预计可售天数", "风险类型", "提示依据"]),
                    width="stretch",
                    hide_index=True,
                )
            if not result.missed_orders.empty:
                st.dataframe(shown(result.missed_orders), width="stretch", hide_index=True)


def render_expiry(result: AnalysisResult) -> None:
    page_intro(
        "临期与过期提示",
        "优先依据包装标注到期日；未填写时，按进货日期加保质期估算到期日。",
    )
    expiry = result.expiry_batches
    expiry_styles = {
        "已到期": "urgent",
        "7天内临期": "expiry",
        "8至30天临期": "review",
    }
    counts = {
        label: (
            int(expiry.loc[expiry["临期类型"] == label, "商品键"].nunique())
            if not expiry.empty
            else 0
        )
        for label in expiry_styles
    }
    cards = "".join(
        f'<div class="risk-card {expiry_styles[label]}"><div class="risk-name">{escape(label)}商品</div>'
        f'<div class="risk-value">{counts[label]}</div></div>'
        for label in expiry_styles
    )
    st.markdown(f'<div class="metric-grid expiry-grid">{cards}</div>', unsafe_allow_html=True)

    if expiry.empty:
        st.success("在已有有效保质信息的库存中，未发现已过期或 30 天内临期商品。")
    else:
        expired_batches = int((expiry["临期类型"] == "已到期").sum())
        if expired_batches:
            st.error(f"发现 {expired_batches} 个已到期库存批次，请优先核对并处理下架。")
        st.subheader("需要处理的库存批次")
        render_priority_cards(result)
        with st.expander("展开查看详细表格"):
            st.dataframe(
                shown(
                    expiry,
                    [
                        "临期类型",
                        "商品名",
                        "批次库存",
                        "单位",
                        "到期日期",
                        "距到期天数",
                        "到期日来源",
                        "进货日期",
                        "保质期（天）",
                        "货架位置",
                        "条码",
                        "品类",
                    ],
                ),
                width="stretch",
                hide_index=True,
            )

    missing_expiry = result.quality_issues[
        result.quality_issues["问题类型"].isin(
            ["临期信息不足", "无效日期", "无效保质期", "到期日期不一致"]
        )
    ]
    st.subheader("保质信息核对")
    if missing_expiry.empty:
        st.caption("当前提交的数据未发现会影响临期判断的保质信息问题。")
    else:
        st.warning("以下商品的临期信息需复核；缺少有效日期的数据不会生成确定的过期提示。")
        with st.expander("展开查看详细表格"):
            st.dataframe(
                shown(missing_expiry, ["问题类型", "商品名", "条码", "问题说明"]),
                width="stretch",
                hide_index=True,
            )


def render_anomalies(result: AnalysisResult) -> None:
    page_intro("异常商品清单", "集中查看库存、销量和临期相关的异常商品。")
    pending = result.products[result.products["数据状态"] != "可分析"].copy()
    pending["风险类型"] = "待核对"
    pending["提示依据"] = pending["数据状态"]
    pending["预计可售天数"] = pd.NA
    combined = pd.concat([result.anomalies, pending], ignore_index=True)
    if combined.empty:
        st.success("未发现满足当前规则的库存异常。")
        return
    categories = sorted(value for value in combined["品类"].dropna().unique() if value)
    risk_types = ["快缺货", "库存偏高", "疑似滞销", "临期风险", "待核对"]
    left, middle, right = st.columns(3)
    selected_categories = left.multiselect("按品类筛选", categories)
    selected_risks = middle.multiselect("按风险类型筛选", risk_types)
    include_pending = right.checkbox("显示待核对商品", value=True)
    filtered = combined.copy()
    if selected_categories:
        filtered = filtered[filtered["品类"].isin(selected_categories)]
    if selected_risks:
        filtered = filtered[
            filtered["风险类型"].map(lambda value: any(risk in value for risk in selected_risks))
        ]
    if not include_pending:
        filtered = filtered[filtered["风险类型"] != "待核对"]
    columns = [
        "商品名",
        "条码",
        "品类",
        "当前库存",
        "单位",
        "近7天销量",
        "预计可售天数",
        "最早到期日",
        "已到期库存",
        "7天内临期库存",
        "8至30天临期库存",
        "货架位置",
        "风险类型",
        "提示依据",
    ]
    with st.expander("展开查看详细表格", expanded=True):
        st.dataframe(shown(filtered, columns), width="stretch", hide_index=True)
    if not result.expiry_batches.empty:
        with st.expander("查看临期批次明细"):
            st.dataframe(shown(result.expiry_batches), width="stretch", hide_index=True)


def render_plan(result: AnalysisResult) -> None:
    page_intro("进货单自查", "结合当前库存复核本次计划进货数量。")
    if not result.plan_uploaded:
        message_without_plan()
        return
    if result.plan_review.empty:
        st.info("计划进货单中没有可展示的商品记录。")
        return
    st.caption("风险提示用于提醒复核现有库存、临期批次、陈列与实际需求，不构成强制结论。")
    with st.expander("展开查看详细表格", expanded=True):
        st.dataframe(shown(result.plan_review), width="stretch", hide_index=True)


def render_missed(result: AnalysisResult) -> None:
    page_intro("可能漏订清单", "识别即将缺货但未被计划进货覆盖的商品。")
    if not result.plan_uploaded:
        message_without_plan()
        return
    if result.missed_orders.empty:
        st.success("未发现可确定提示为可能漏订的快缺货商品。")
        return
    with st.expander("展开查看详细表格", expanded=True):
        st.dataframe(shown(result.missed_orders), width="stretch", hide_index=True)


def render_export(
    result: AnalysisResult, analysis_date, inventory_name: str, plan_name: str | None
) -> None:
    page_intro("导出结果", "下载本次复核记录，便于留档或再次核对。")
    st.write("导出文件包含分析说明、数据质量问题、异常、临期批次、进货自查与可能漏订清单。")
    export_bytes = build_export_workbook(
        result,
        analysis_date,
        {"inventory": inventory_name, "plan": plan_name or "未上传"},
        datetime.now(STORE_TIMEZONE),
    )
    st.download_button(
        "下载自查结果 Excel",
        export_bytes,
        f"补货自查结果_{analysis_date.isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
    if not result.plan_uploaded:
        st.caption("未上传计划进货单；导出的相应工作表会注明未执行该分析。")


def render_rules(analysis_date) -> None:
    page_intro("规则说明", "查看当前版本使用的透明判断口径。")
    st.write(f"规则版本：`{RULESET_VERSION}`　|　分析日期：`{analysis_date.isoformat()}`")
    rule_table = pd.DataFrame(
        [
            ["快缺货", "近7天销量 > 0，预计可售天数 <= 3 天"],
            ["库存偏高", "近7天销量 > 0，预计可售天数 > 30 天"],
            ["疑似滞销", "近7天销量 = 0 且当前库存 > 0"],
            ["到期日计算", "优先采用标注到期日期；未填写时按进货日期 + 保质期（天）估算"],
            ["已到期", "计算得到的到期日期 <= 分析日期，且该批库存仍有库存"],
            ["7天内临期", "计算得到的到期日期在分析日期后 1 至 7 天，且仍有库存"],
            ["8至30天临期", "计算得到的到期日期在分析日期后 8 至 30 天，且仍有库存"],
            ["可能进货过量", "进货后预计可售天数 > 45 天"],
            ["可能漏订", "符合快缺货，且未匹配到正数计划进货数量"],
        ],
        columns=["提示类型", "判断依据"],
    )
    st.dataframe(rule_table, width="stretch", hide_index=True)
    st.subheader("数据不足时如何处理")
    st.write(
        "商品身份冲突、同商品不同进货批次销量不一致、数量非法或单位不一致时，"
        "系统会显示待核对，不用不完整数据生成确定性补货结论。"
    )
    st.write("缺少标注到期日期，且未同时填写进货日期和保质期时，系统仍可进行库存分析，但不生成该行的确定性临期结论。")
    st.subheader("为什么不自动给出补货量")
    st.write(
        "首版未采集安全库存、供应提前期、整箱倍数和在途订单等信息，"
        "因此只提供透明的复核提示，不将不完整条件包装成精确采购建议。"
    )


require_password()
initialise_direct_entry()
st.markdown(
    '<div class="mobile-brand"><span class="brand-mark">✓</span>零食门店商品动销与批次临期管理助手</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        '<div class="sidebar-brand"><span class="brand-mark">✓</span>'
        "<span>零食门店商品动销<br>与批次临期管理助手</span></div>",
        unsafe_allow_html=True,
    )
    page = st.radio(
        "功能导航",
        [
            "首页总览",
            "数据录入",
            "数据质量核对",
            "今日重点提醒",
            "临期与过期提示",
            "异常商品清单",
            "进货单自查",
            "可能漏订清单",
            "导出结果",
            "规则说明",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    st.subheader("本次自查")
    today = datetime.now(STORE_TIMEZONE).date()
    analysis_date = st.date_input("分析日期", value=today, help="临期判断以该日期为基准。")
    input_mode = st.radio("录入方式", ["直接填写", "上传表格"], horizontal=True)
    inventory_upload = None
    plan_upload = None
    if input_mode == "上传表格":
        inventory_upload = st.file_uploader("库存销售表", type=["xlsx", "csv"])
        plan_upload = st.file_uploader("计划进货单（可选）", type=["xlsx", "csv"])
    else:
        st.caption("请在“数据录入”步骤直接填写商品情况。")
    st.markdown(
        f'<div class="sidebar-note"><strong>ⓘ 结果说明</strong>'
        f"规则版本：{RULESET_VERSION}<br>本地分析，不含考核与排名</div>",
        unsafe_allow_html=True,
    )

result: AnalysisResult | None = None
inventory_name: str | None = None
plan_name: str | None = None
analysis_source = ""
if input_mode == "直接填写" and st.session_state["direct_inventory_submitted"] is not None:
    inventory_frame = st.session_state["direct_inventory_submitted"]
    plan_frame = st.session_state["direct_plan_submitted"]
    inventory_name = "页面直接填写_库存销售"
    plan_name = "页面直接填写_计划进货" if plan_frame is not None else None
    analysis_source = st.session_state["direct_data_origin"]
    result = analyse(inventory_frame, plan_frame, analysis_date)
elif input_mode == "上传表格" and inventory_upload is not None:
    try:
        inventory_frame = load_uploaded(inventory_upload.getvalue(), inventory_upload.name)
        plan_frame = (
            load_uploaded(plan_upload.getvalue(), plan_upload.name)
            if plan_upload is not None
            else None
        )
        result = analyse(inventory_frame, plan_frame, analysis_date)
        inventory_name = inventory_upload.name
        plan_name = plan_upload.name if plan_upload else None
        analysis_source = f"上传文件：{inventory_upload.name}"
    except InputReadError as error:
        st.error(str(error))

if page == "首页总览":
    render_home(result, analysis_source)
elif page == "数据录入":
    render_entry(input_mode, inventory_upload, plan_upload, result)
elif page == "规则说明":
    render_rules(analysis_date)
elif result is None:
    st.info("请先在“数据录入”步骤直接填写或上传库存销售信息，再查看分析结果。")
elif page == "数据质量核对":
    render_quality(result)
elif page == "今日重点提醒":
    render_summary(result, analysis_source)
elif page == "临期与过期提示":
    render_expiry(result)
elif page == "异常商品清单":
    render_anomalies(result)
elif page == "进货单自查":
    render_plan(result)
elif page == "可能漏订清单":
    render_missed(result)
elif page == "导出结果":
    render_export(
        result,
        analysis_date,
        inventory_name or "",
        plan_name,
    )
