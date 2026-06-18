import akshare as ak
import requests
import os
from datetime import datetime

# ========== 用户配置区域（请修改这里） ==========
# 1. 你的基金持仓：格式 { '基金代码': {'shares': 持有份额, 'cost': 成本单价} }
#    例如：持有 1000 份 510300，成本价 3.5 元/份；持有 500 份 005827，成本价 1.2 元/份
PORTFOLIO = {
    '021778': {'shares': 1000, 'cost': 3.5},
    '005693': {'shares': 500,  'cost': 1.2},
}

# 2. 为了兼容，自动从 PORTFOLIO 提取基金代码列表
FUND_LIST = list(PORTFOLIO.keys())

# 3. 密钥（从 GitHub Secrets 读取，不要手动填写）
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
# ===============================================

def get_fund_data(code):
    """获取基金最新净值，尝试多种方法"""
    # 方法1：ETF
    try:
        df = ak.fund_etf_hist_em(symbol=code)
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            nav = latest.get('净值')
            date = latest.get('日期')
            if nav is not None:
                return {'code': code, 'nav': nav, 'date': date}
    except:
        pass

    # 方法2：开放式基金
    try:
        df = ak.fund_em_open_fund_info(fund=code, indicator="单位净值走势")
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            nav = latest.get('单位净值')
            date = latest.get('净值日期')
            if nav is not None:
                return {'code': code, 'nav': nav, 'date': date}
    except:
        pass

    # 方法3：实时估值（部分基金）
    try:
        df = ak.fund_em_valuation_real_time(symbol=code)
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            nav = latest.get('最新净值')
            date = datetime.now().strftime('%Y-%m-%d')
            if nav is not None:
                return {'code': code, 'nav': nav, 'date': date}
    except:
        pass

    print(f"⚠️ 无法获取基金 {code} 的数据")
    return None

def analyze_with_deepseek(fund_data_list, portfolio):
    """调用 DeepSeek API，结合持仓进行分析"""
    if not DEEPSEEK_API_KEY:
        return "⚠️ 错误：未设置 DeepSeek API Key。"

    # 构建持仓信息和市值
    total_value = 0
    lines = []
    for item in fund_data_list:
        code = item['code']
        nav = item['nav']
        shares = portfolio[code]['shares']
        cost = portfolio[code]['cost']
        market_value = nav * shares
        profit = (nav - cost) * shares
        profit_rate = (nav / cost - 1) * 100 if cost > 0 else 0
        total_value += market_value
        lines.append(
            f"- {code}: 持有{shares}份，成本{cost:.4f}，现价{nav:.4f}，"
            f"市值{market_value:.2f}，盈亏{profit:+.2f} ({profit_rate:+.2f}%)"
        )

    funds_text = "\n".join(lines)
    total_text = f"总资产：{total_value:.2f}"

    prompt = f"""
    你是专业基金顾问，根据以下持仓数据和市场情况，提供个性化分析和建议。
    当前日期：{datetime.now().strftime('%Y-%m-%d')}

    【持仓明细】
    {funds_text}
    {total_text}

    请分析：
    1. 持仓结构评价（集中度、风险分散情况）
    2. 根据当前净值变化，给出调仓建议（加仓/减仓/持有）
    3. 强调潜在风险

    回答简洁，控制在 300 字内。
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
    if not FEISHU_WEBHOOK:
        return
    data = {"msg_type": "text", "content": {"text": message}}
    try:
        requests.post(FEISHU_WEBHOOK, json=data, timeout=10)
    except Exception as e:
        print(f"发送失败: {e}")

if __name__ == "__main__":
    print("🚀 开始获取基金数据...")

    # 获取所有基金净值
    valid_data = []
    for code in FUND_LIST:
        data = get_fund_data(code)
        if data:
            valid_data.append(data)
            print(f"✅ 获取 {code} 成功: 净值 {data['nav']}")
        else:
            print(f"❌ 获取 {code} 失败")

    if not valid_data:
        error_msg = f"❌ 所有基金数据获取失败，请检查代码。"
        send_to_feishu(error_msg)
        print(error_msg)
        exit(1)

    print("📊 数据获取完成，正在调用 AI 分析（包含持仓）...")
    ai_analysis = analyze_with_deepseek(valid_data, PORTFOLIO)

    # 构建报告（包含详细的持仓盈亏）
    report = f"📈 **基金持仓日报 - {datetime.now().strftime('%Y-%m-%d')}**\n\n"
    total = 0
    for item in valid_data:
        code = item['code']
        nav = item['nav']
        shares = PORTFOLIO[code]['shares']
        cost = PORTFOLIO[code]['cost']
        market_val = nav * shares
        profit = (nav - cost) * shares
        profit_rate = (nav / cost - 1) * 100 if cost > 0 else 0
        total += market_val
        report += (
            f"**{code}**\n"
            f"  持有: {shares} 份\n"
            f"  成本: {cost:.4f}，现价: {nav:.4f}\n"
            f"  市值: {market_val:.2f}，盈亏: {profit:+.2f} ({profit_rate:+.2f}%)\n\n"
        )
    report += f"**总资产**: {total:.2f}\n\n"
    report += f"**🤖 AI 策略建议**\n{ai_analysis}"

    print("📨 推送到飞书...")
    send_to_feishu(report)
    print("🎉 任务完成！")
