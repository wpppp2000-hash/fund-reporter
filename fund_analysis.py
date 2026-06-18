import akshare as ak
import requests
import os
from datetime import datetime

# --- 配置区域（请修改这里）---
# 1. 你的基金代码列表
FUND_LIST = ['021778', '005693', '022460']  # <--- 改成你的基金代码
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
# -----------------------------

def get_fund_data(code):
    """获取基金最新净值，尝试多种方法"""
    # 方法1：ETF 基金（如 510300）
    try:
        df = ak.fund_etf_hist_em(symbol=code)
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            nav = latest.get('净值')
            date = latest.get('日期')
            if nav is not None:
                return {'code': code, 'nav': nav, 'date': date}
    except Exception:
        pass

    # 方法2：开放式基金（如 005827）
    try:
        df = ak.fund_em_open_fund_info(fund=code, indicator="单位净值走势")
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            nav = latest.get('单位净值')
            date = latest.get('净值日期')
            if nav is not None:
                return {'code': code, 'nav': nav, 'date': date}
    except Exception:
        pass

    # 方法3：尝试获取实时估值（针对部分基金）
    try:
        df = ak.fund_em_valuation_real_time(symbol=code)
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            nav = latest.get('最新净值')
            date = datetime.now().strftime('%Y-%m-%d')
            if nav is not None:
                return {'code': code, 'nav': nav, 'date': date}
    except Exception:
        pass

    # 如果所有方法都失败
    print(f"⚠️ 无法获取基金 {code} 的数据")
    return None

def analyze_with_deepseek(fund_data_list):
    """调用 DeepSeek API 分析基金数据"""
    if not DEEPSEEK_API_KEY:
        return "⚠️ 错误：未设置 DeepSeek API Key。"

    funds_text = "\n".join([f"- {f['code']}: 净值 {f['nav']} (日期: {f['date']})" for f in fund_data_list])
    prompt = f"""
    作为专业基金分析师，根据以下基金的最新净值数据，提供简短分析和建议。
    当前日期：{datetime.now().strftime('%Y-%m-%d')}

    基金数据：
    {funds_text}

    分析：
    1. 整体评价
    2. 投资策略建议
    3. 风险提示

    控制在 200 字内。
    """

    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"⚠️ AI分析失败: {e}"

def send_to_feishu(message):
    """发送消息到飞书"""
    if not FEISHU_WEBHOOK:
        return
    data = {"msg_type": "text", "content": {"text": message}}
    try:
        requests.post(FEISHU_WEBHOOK, json=data, timeout=10)
    except Exception as e:
        print(f"发送失败: {e}")

if __name__ == "__main__":
    print("🚀 开始获取基金数据...")
    
    # 获取所有基金数据
    valid_data = []
    for code in FUND_LIST:
        data = get_fund_data(code)
        if data:
            valid_data.append(data)
            print(f"✅ 获取 {code} 成功: 净值 {data['nav']}")
        else:
            print(f"❌ 获取 {code} 失败")

    if not valid_data:
        error_msg = f"❌ 所有基金数据获取失败 (共 {len(FUND_LIST)} 只)\n请检查基金代码是否正确。"
        send_to_feishu(error_msg)
        print(error_msg)
        exit(1)

    print(f"📊 成功获取 {len(valid_data)} 只基金数据，正在调用 AI 分析...")
    ai_analysis = analyze_with_deepseek(valid_data)

    report = f"📈 **基金日报 - {datetime.now().strftime('%Y-%m-%d')}**\n\n"
    report += "**📊 净值数据**\n"
    for f in valid_data:
        report += f"- {f['code']}: {f['nav']} (日期: {f['date']})\n"
    
    # 如果有基金获取失败，在报告中注明
    failed_count = len(FUND_LIST) - len(valid_data)
    if failed_count > 0:
        report += f"\n⚠️ 有 {failed_count} 只基金未能获取数据\n"

    report += f"\n**🤖 AI 分析报告**\n{ai_analysis}"

    print("📨 推送到飞书...")
    send_to_feishu(report)
    print("🎉 任务完成！")
