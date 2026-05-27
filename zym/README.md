# 零食门店商品动销与批次临期管理助手

这是一个基于 Streamlit 的轻量网页工具，用于零食门店在补货前快速自查商品动销、库存风险与批次临期情况。项目已整理为可部署到 Streamlit Community Cloud 的公网版本。

## 项目功能

- 直接录入或上传商品销售库存数据。
- 按商品名、进货日期、当前库存、库存/销售单位、近 7 天销量、近 30 天销量、保质期等字段进行分析。
- 提示快缺货、库存偏高、疑似滞销、临期/过期、进货风险和可能漏订。
- 首页用卡片展示重点指标，今日重点处理清单优先用卡片呈现，适合手机访问。
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
