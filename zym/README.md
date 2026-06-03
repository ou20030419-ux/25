# 零食门店商品动销与批次临期管理助手

这是一个基于 Streamlit 的轻量网页工具，用于零食门店在补货前快速自查商品动销、库存风险与批次临期情况。项目已整理为可部署到 Streamlit Community Cloud 的公网版本。

## 项目功能

- 直接录入或上传商品销售库存数据。
- 直接录入表按 10 行一段录入，并分为“销量信息录入”和“临期信息录入”两大类。
- 单位合并为一个输入栏，可直接填写常用单位或自定义单位；临期信息可记录货架位置与仓库位置。
- 按商品名、进货日期、上次进货总量、本进货周期销量、库存剩余量、库存/销售单位、近 30 天销量、保质期等字段进行分析。
- 销量相关计算以一次统一进货周期为基准：快缺货、库存偏高、进货后库存和可能漏订都按“本进货周期销量”估算。
- 库存剩余量可手动填写；未填写时系统会按“上次进货总量 - 本进货周期销量”自动计算。
- 提示快缺货、库存偏高、疑似滞销、临期/过期、进货风险和可能漏订。
- 首页用卡片展示重点指标，本次重点处理清单优先用卡片呈现，适合手机访问。
- 首页增加“本周期工作台”，把数据录入、本次重点、30 天历史归档和导出放到页面中间，减少只依赖左侧导航的问题。
- 支持 30 天历史归档：按每次录入保存分析快照，可导入上次归档继续累计，并自动汇总“稳定好卖、本周期需要补货、库存偏高、持续滞销”等商品分层。
- 宽表格放在“展开查看详细表格”中，避免手机端首屏拥挤。
- 保留 Excel 导出功能，便于复核和留档。

## 项目结构

部署根目录至少包含：

```text
app.py
requirements.txt
README.md
示例数据/
  商品销售库存表模板.xlsx
  批次库存表模板.xlsx
```

## 本地运行方法

在项目根目录打开终端：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

macOS 或 Linux 可使用：

```bash
source .venv/bin/activate
streamlit run app.py
```

本地运行前也需要配置 `APP_PASSWORD`。可在项目根目录创建 `.streamlit/secrets.toml`：

```toml
APP_PASSWORD = "请改成你自己的访问密码"
```

## Streamlit Community Cloud 部署方法

1. 将本项目推送到 GitHub 仓库。
2. 打开 [Streamlit Community Cloud](https://streamlit.io/cloud)。
3. 选择该 GitHub 仓库。
4. Main file path 填写：

```text
app.py
```

5. 在应用的 Secrets 设置中添加：

```toml
APP_PASSWORD = "请改成你自己的访问密码"
```

6. 保存后部署。页面打开后会先要求输入访问密码。

## requirements.txt 的作用

`requirements.txt` 用来告诉 Streamlit Community Cloud 安装项目依赖。当前包含：

- `streamlit`：网页应用框架。
- `pandas`：表格数据处理。
- `openpyxl`：读取和生成 `.xlsx` 文件。
- `xlsxwriter`：Excel 写入兼容依赖。
- `python-dateutil`：日期处理兼容依赖。
- `qrcode`：二维码生成预留依赖。
- `pillow`：图片处理预留依赖。

## APP_PASSWORD 配置说明

密码不会写死在代码中，应用通过以下方式读取：

```python
st.secrets["APP_PASSWORD"]
```

如果未配置 `APP_PASSWORD`，页面会提示“请先配置 APP_PASSWORD”，并停止加载业务页面。

## 连续 30 天使用建议

公网版本不建议依赖服务器本地硬盘长期保存数据。建议每个进货周期按以下方式使用：

1. 在“数据录入”中填写或上传上次进货总量、本进货周期销量、库存剩余量、进货日期、保质期等数据。
2. 提交后进入“30天历史归档”，点击“保存本次到30天归档”。
3. 下载“30天归档 Excel”留存。
4. 下次打开网页后，先上传上次下载的归档 Excel，再保存本次数据。

这样即使 Streamlit Community Cloud 重启应用，也可以通过 Excel 归档继续累计最近 30 天记录。
累计 2 次以上进货周期后，“30天历史归档”页会根据多次销量、最近库存和重复风险给出商品经营分层，帮助判断哪些是真好卖、哪些应减少进货。

## 数据安全提醒

公网版本适合演示、培训或低敏数据自查。不建议上传真实门店敏感数据，例如完整门店销售明细、客户信息、供应链价格、内部考核资料或其他不适合公开托管环境处理的数据。

## 示例数据

`示例数据` 文件夹中包含两个空白 Excel 模板：

- `商品销售库存表模板.xlsx`
- `批次库存表模板.xlsx`

模板字段与应用上传入口兼容，可下载后按实际门店情况填写。

## 测试

```powershell
python -m unittest discover -s tests -v
```
