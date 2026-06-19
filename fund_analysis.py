import requests
import os
import re
from datetime import datetime

# ========== 用户配置区域 ==========
INVESTMENT_STYLE = "进取型（最大可承受10-20%回撤）"
TIME_HORIZON = 3

# 仓位配置
BASE_FUND = '022460'
SATELLITE_FUNDS = ['005693', '011613', '021778']

# 持仓信息：新增 type 字段
# - 'normal': 普通基金（计算盈亏）
# - 'money': 货币基金（只显示份额和费率，不计算盈亏）
PORTFOLIO = {
    '021778': {'shares': 213, 'cost': 8.4396, 'type': 'normal'},
    '005693': {'shares': 4252, 'cost': 1.176, 'type': 'normal'},
    '022460': {'shares': 13794, 'cost': 1.305, 'type': 'normal'},
    '011613': {'shares': 1606, 'cost': 1.432, 'type': 'normal'},
    '012857': {'shares': 651, 'cost': 1.767, 'type': 'normal'},
    '007467': {'shares': 623, 'cost': 1.602, 'type': 'normal'},
    # 示例：货币基金（假设你持有一支货币基金，代码和份额请自行替换）
    # '004368': {'shares': 10000, 'fee_rate': 0.375, 'type': 'money'},  # 费率0.33%/年
}
FUND_LIST = list(PORTFOLIO.keys())

# 密钥
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
SERPER_API_KEY = os.environ.get('SERPER_API_KEY')
# ==================================

def get_fund_name(code):
    try:
        url = f"https://fund.eastmoney.com/{code}.html"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"
        html = resp.text
        match = re.search(r'<title>(.*?)基金净值', html)
        if match:
            return match.group(1).strip()
        match = re.search(r'<h1 class="fundName">(.*?)</h1>', html)
        if match:
            return match.group(1).strip()
    except:
        pass
    return code

def get_fund_nav_sina(code):
    try:
        url = f"https://hq.sinajs.cn/list=f_{code}"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "gbk"
        data = resp.text
        if "var hq_str_f_" in data:
            parts = data.split('"')[1].split(',')
            if len(parts) >= 5:
                return {'code': code, 'nav': float(parts[1]), 'date': parts[3]}
    except:
        pass
    return None

def get_fund_nav_eastmoney(code):
    try:
        url = f"https://fund.eastmoney.com/{code}.html"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"
        html = resp.text
        match = re.search(r'<span class="data_item01">([\d.]+)</span>', html)
        if not match:
            match = re.search(r'净值：([\d.]+)', html)
        if match:
            nav = float(match.group(1))
            date_match = re.search(r'净值日期：(\d{4}-\d{2}-\d{2})', html)
            date = date_match.group(1) if date_match else datetime.now().strftime('%Y-%m-%d')
            return {'code': code, 'nav': nav, 'date': date}
    except:
        pass
    return None

def get_position_type(code):
    if code == BASE_FUND:
        return "【底仓】"
    elif code in SATELLITE_FUNDS:
        return "【卫星仓】"
    return ""

def search_news(query, api_key):
    if not api_key:
        return "未配置 Serper API Key，无法获取实时新闻。"
    url = "https://google.serper.dev/news"
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": 5}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code != 200:
            return f"搜索失败，HTTP {resp.status_code}"
        data = resp.json()
        news_items = data.get('news', [])
        if not news_items:
            return "未找到相关新闻。"
        news_lines = []
        for idx, item in enumerate(news_items[:5], 1):
            title = item.get('title', '')
            snippet = item.get('snippet', '')
            link = item.get('link', '')
            if len(snippet) > 150:
                snippet = snippet[:150] + "..."
            news_lines.append(f"{idx}. {title}\n   {snippet}\n   链接: {link}")
        return "\n\n".join(news_lines)
    except Exception as e:
        return f"搜索异常: {str(e)}"

def analyze_with_deepseek(fund_data_list, portfolio):
    if not DEEPSEEK_API_KEY:
        return "⚠️ 未设置 DeepSeek API Key"

    # 构建持仓详情（区分普通基金和货币基金）
    lines = []
    total = 0
    money_fund_lines = []

    for item in fund_data_list:
        code = item['code']
        nav = item['nav']
        config = portfolio[code]
        shares = config['shares']
        fund_type = config.get('type', 'normal')
        name = get_fund_name(code)
        pos_type = get_position_type(code)

        if fund_type == 'money':
            fee_rate = config.get('fee_rate', 0.0033)
            money_fund_lines.append(
                f"- {code} {name} {pos_type} 【货币基金】: 持有{shares}份，"
                f"费率{fee_rate*100:.2f}%/年（每日计提），净值恒为1.00"
            )
            continue

        cost = config['cost']
        market = nav * shares
        profit = (nav - cost) * shares
        rate = (nav / cost - 1) * 100 if cost > 0 else 0
        total += market
        lines.append(
            f"- {code} {name} {pos_type}: 持有{shares}份，成本{cost:.4f}，现价{nav:.4f}，"
            f"市值{market:.2f}，盈亏{profit:+.2f} ({rate:+.2f}%)"
        )

    funds_text = "\n".join(lines)
    if money_fund_lines:
        funds_text += "\n\n【货币基金】（不参与盈亏计算）：\n" + "\n".join(money_fund_lines)

    total_text = f"{total:.2f}"

    strategy_text = f"""
【仓位策略】
- 底仓（{BASE_FUND}）：核心资产，长期持有，不减仓，止损线-20%
- 卫星仓（{', '.join(SATELLITE_FUNDS)}）：灵活配置，波段操作，止损线-10%
- 其他普通仓：按常规逻辑分析，止损线-10%
"""

    today = datetime.now().strftime('%Y-%m-%d')
    news_query = f"A股 热点 板块 资金流向 {today}"
    print("🔍 正在搜索今日市场动态...")
    news_text = search_news(news_query, SERPER_API_KEY)
    if "未配置" in news_text or "失败" in news_text:
        print(f"⚠️ {news_text}")
    else:
        print("✅ 新闻获取成功")

    # ===================== 新的 stock9300 风格 prompt =====================
    prompt = f"""
你是一位严谨、果断的投资顾问，风格类似“stock9300”那样的量化投顾。你的回答必须**直接、量化、有明确信号**，不要写散文。

【今日实时市场动态】（来自 Google 搜索）
{news_text}

【我的持仓】
{funds_text}
总资产（不含货币基金）：{total_text}
{strategy_text}
风险偏好：{INVESTMENT_STYLE}，可承受10-20%回撤。

【任务】
请按以下格式输出，每只基金单独一段：

---
**基金代码 基金名称 【仓位类型】**
- 当前净值：X.XXXX
- 持有份额：XXXX
- 盈亏：+/-XX.XX%
- **操作信号**：【买入/加仓/持有/减仓/卖出】（明确选择）
- **信号强度**：【高/中/低】
- **逻辑**：用1-2句话说明为什么（结合新闻、估值、趋势）。
- **目标价位**：止损价 X.XX，止盈价 X.XX（若适用）。

---

**整体市场判断**：（一句话，如“震荡偏多，结构性机会在科技”）
**当前最大风险**：（一句话）
**建议关注的新方向**：（1-2个板块/基金，给出代码和理由）

---

【硬性要求】
- 每只基金必须有明确的“操作信号”，不要模糊。
- 信号必须基于今日新闻和持仓数据，逻辑清晰。
- 不要使用“可能”、“或许”等模糊词。
- 总字数控制在 800 字以内。

当前日期：{datetime.now().strftime('%Y-%m-%d')}
"""
    # =====================================================================

    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 3000,
        "temperature": 0.8
    }

    for attempt in range(2):
        try:
            print(f"🧠 请求 DeepSeek API (尝试 {attempt+1}/2)...")
            resp = requests.post(url, headers=headers, json=payload, timeout=90)
            print(f"📡 HTTP: {resp.status_code}")
            if resp.status_code != 200:
                return f"⚠️ API错误 {resp.status_code}: {resp.text[:100]}"
            result = resp.json()
            content = result['choices'][0].get('message', {}).get('content', '')
            if not content or content.strip() == '':
                return "⚠️ API返回空内容，请重试"
            print(f"✅ 分析成功，{len(content)}字符")
            return content
        except requests.exceptions.Timeout:
            print(f"⏱️ 超时 (尝试 {attempt+1}/2)")
            if attempt == 1:
                return "⚠️ 两次超时，请稍后重试"
            continue
        except Exception as e:
            return f"⚠️ 分析失败: {e}"
    return "⚠️ 未知错误"

def send_to_feishu(message):
    if not FEISHU_WEBHOOK:
        return
    data = {"msg_type": "text", "content": {"text": message}}
    try:
        r = requests.post(FEISHU_WEBHOOK, json=data, timeout=10)
        if r.status_code == 200:
            print("✅ 飞书推送成功")
        else:
            print(f"❌ 推送失败: {r.status_code}")
    except Exception as e:
        print(f"❌ 异常: {e}")

if __name__ == "__main__":
    print("🚀 开始获取基金数据...")
    print(f"📌 基金: {FUND_LIST}")

    valid_data = []
    for code in FUND_LIST:
        print(f"🔍 获取 {code}...")
        data = get_fund_nav_sina(code)
        if not data:
            data = get_fund_nav_eastmoney(code)
        if data:
            valid_data.append(data)
            print(f"✅ {code} 净值 {data['nav']}")
        else:
            print(f"❌ {code} 失败")

    if not valid_data:
        send_to_feishu("❌ 所有基金数据获取失败")
        exit(1)

    print(f"📊 成功获取 {len(valid_data)} 只基金")
    print("🧠 调用 DeepSeek 分析...")
    ai_analysis = analyze_with_deepseek(valid_data, PORTFOLIO)

    report = f"📈 **基金持仓日报 - {datetime.now().strftime('%Y-%m-%d')}**\n\n"
    total_value = 0
    for item in valid_data:
        code = item['code']
        nav = item['nav']
        config = PORTFOLIO[code]
        shares = config['shares']
        fund_type = config.get('type', 'normal')
        name = get_fund_name(code)
        pos_type = get_position_type(code)

        if fund_type == 'money':
            fee_rate = config.get('fee_rate', 0.0033)
            report += (
                f"**{code} {name} {pos_type} 【货币基金】**\n"
                f"  持有: {shares} 份\n"
                f"  费率: {fee_rate*100:.2f}%/年（每日计提）\n"
                f"  净值恒为: 1.00\n\n"
            )
        else:
            cost = config['cost']
            market = nav * shares
            profit = (nav - cost) * shares
            rate = (nav / cost - 1) * 100 if cost > 0 else 0
            total_value += market
            report += (
                f"**{code} {name} {pos_type}**\n"
                f"  持有: {shares} 份\n"
                f"  成本: {cost:.4f} → 现价: {nav:.4f}\n"
                f"  盈亏: {profit:+.2f} ({rate:+.2f}%)\n\n"
            )

    report += f"**总资产（不含货币基金）**: {total_value:.2f}\n\n"
    report += f"**🤖 投资大师评述**\n{ai_analysis}"

    send_to_feishu(report)
    print("🎉 任务完成！")
