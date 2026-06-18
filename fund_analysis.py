import akshare as ak
import requests
import os
from datetime import datetime

# --- 配置区域（请修改这里）---
# 1. 你的基金代码列表（用英文逗号分隔，字符串形式）
FUND_LIST = ['021778', '005693', '022460', '011613', '007467', '012857']  # <--- 改成你的基金代码
# 2. 以下两个从 GitHub Secrets 读取，不要手动填写
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
# -----------------------------

def get_fund_data(code):
    """获取基金最新净值"""
    try:
        # 尝试获取 ETF 基金数据
        df = ak.fund_etf_hist_em(symbol=code)
    except Exception:
        try:
            # 若失败，尝试获取开放式基金数据
            df = ak.fund_em_open_fund_info(fund=code, indicator="单位净值走势")
        except Exception as e:
            print(f"获取基金 {code} 数据失败: {e}")
            return None

    if df is not None and not df.empty:
        latest = df.iloc[-1]
        nav = latest.get('净值', latest.get('单位净值', None))
        date = latest.get('日期', latest.get('净值日期', datetime.now().strftime('%Y-%m-%d')))
        return {'code': code, 'nav': nav, 'date': date}
    return None

def analyze_with_deepseek(fund_data_list):
    """调用 DeepSeek API 分析基金数据"""
    if not DEEPSEEK_API_KEY:
        return "⚠️ 错误：未设置 DeepSeek API Key。"

    funds_text = "\n".join([f"- {f['code']}: 净值 {f['nav']} (日期: {f['date']})" for f in fund_data_list if f])
    prompt = f"""
    作为一位专业的基金分析师，请根据以下基金的最新净值数据，提供一份简短的市场分析和投资建议。
    当前日期：{datetime.now().strftime('%Y-%m-%d')}

    基金数据：
    {funds_text}

    请分析：
    1. 对这些基金近期表现的整体评价。
    2. 结合当前市场环境，给出简短的投资策略建议。
    3. 提示任何需要关注的风险点。

    回答请简洁，控制在 300 字以内。
    """

    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-v4-flash",  # 可用 deepseek-v4-pro
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"⚠️ 调用 DeepSeek API 失败: {e}"

def send_to_feishu(message):
    """发送消息到飞书"""
    if not FEISHU_WEBHOOK:
        print("⚠️ 错误：未设置飞书 Webhook。")
        return
    data = {"msg_type": "text", "content": {"text": message}}
    try:
        response = requests.post(FEISHU_WEBHOOK, json=data)
        response.raise_for_status()
        print("✅ 消息发送成功！")
    except Exception as e:
        print(f"❌ 发送消息到飞书失败: {e}")

if __name__ == "__main__":
    print("🚀 开始获取基金数据...")
    fund_results = [get_fund_data(code) for code in FUND_LIST]
    valid_data = [f for f in fund_results if f]

    if not valid_data:
        send_to_feishu("❌ 获取基金数据失败，请检查基金代码或网络。")
    else:
        print("📊 基金数据获取成功，正在调用 AI 进行分析...")
        ai_analysis = analyze_with_deepseek(valid_data)

        report = f"📈 **基金日报 - {datetime.now().strftime('%Y-%m-%d')}**\n\n"
        report += "**📊 净值数据**\n"
        for f in valid_data:
            report += f"- {f['code']}: {f['nav']} (日期: {f['date']})\n"
        report += f"\n**🤖 AI 分析报告**\n{ai_analysis}"

        print("📨 正在推送到飞书...")
        send_to_feishu(report)
        print("🎉 任务完成！")
