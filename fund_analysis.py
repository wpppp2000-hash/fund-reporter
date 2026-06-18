import requests
import os
import re
from datetime import datetime

# ========== 用户配置区域 ==========
# 投资偏好
INVESTMENT_STYLE = "进取型（最大可承受10-20%回撤）"
TIME_HORIZON = 3

# 仓位配置
BASE_FUND = '022460'
SATELLITE_FUNDS = ['005693', '011613', '021778']

# 持仓信息
PORTFOLIO = {
    '021778': {'shares': 213, 'cost': 8.4396},
    '005693': {'shares': 4252, 'cost': 1.176},
    '022460': {'shares': 13794, 'cost': 1.305},
    '011613': {'shares': 1606, 'cost': 1.432},
    '012857': {'shares': 651, 'cost': 1.767},
    '007467': {'shares': 623, 'cost': 1.602},
}
FUND_LIST = list(PORTFOLIO.keys())

# 密钥
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
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

def analyze_with_deepseek(fund_data_list, portfolio):
    if not DEEPSEEK_API_KEY:
        return "⚠️ 未设置 DeepSeek API Key"

    lines = []
    total = 0
    for item in fund_data_list:
        code = item['code']
        nav = item['nav']
        shares = portfolio[code]['shares']
        cost = portfolio[code]['cost']
        market = nav * shares
        profit = (nav - cost) * shares
        rate = (nav / cost - 1) * 100 if cost > 0 else 0
        total += market
        name = get_fund_name(code)
        pos_type = get_position_type(code)
        lines.append(
            f"- {code} {name} {pos_type}: 持有{shares}份，成本{cost:.4f}，现价{nav:.4f}，"
            f"市值{market:.2f}，盈亏{profit:+.2f} ({rate:+.2f}%)"
        )
    funds_text = "\n".join(lines)
    total_text = f"{total:.2f}"

    strategy_text = f"""
【仓位策略】
- 底仓（{BASE_FUND}）：核心资产，长期持有，不减仓，止损线-20%
- 卫星仓（{', '.join(SATELLITE_FUNDS)}）：灵活配置，波段操作，止损线-10%
- 其他普通仓：按常规逻辑分析，止损线-10%
"""

    prompt = f"""
你是一位纵横华尔街三十年的投资大师，曾亲历多次牛熊转换，既深谙巴菲特的价值投资哲学，也精通索罗斯的反射性理论。

【今日任务】分为两部分：

## 第一部分：持仓诊断（请重点分析）
我的持仓如下：
{funds_text}
总资产：{total_text}
{strategy_text}
风险偏好：{INVESTMENT_STYLE}
投资期限：{TIME_HORIZON}年

请以第一人称对现有持仓进行评述：
1. 逐一评价每只基金的本质（护城河/周期性/成长性）
2. 给出明确的定性判断（"这是好东西"或"这个需要警惕"）
3. 对每只基金给出具体操作指令（加仓/减仓/持有 + 具体份额或比例）
4. 设定清晰的止损价和止盈目标价

## 第二部分：市场机会发现（请务必联网搜索最新信息）
请搜索今日（{datetime.now().strftime('%Y-%m-%d')}）的市场动态，包括：
1. 涨幅居前的板块和ETF
2. 重大政策利好
3. 主力资金流向

基于搜索到的信息，回答：
1. **当前最值得关注的3个投资方向**（板块/主题）
2. **对应的代表性基金**（名称+代码）
3. **建议买入时机**（现在/回调后/分批建仓）
4. **建议持有周期**（短线/中线/长线）
5. **潜在风险提示**

【语言风格要求】
- 第一人称"我"，口语化、有温度
- 多用比喻和类比
- 敢于亮出鲜明观点
- 引用经典投资格言
- 控制在1500字以内

当前日期：{datetime.now().strftime('%Y-%m-%d')}
"""

    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4000,
        "temperature": 0.8,
        "enable_search": True
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
        shares = PORTFOLIO[code]['shares']
        cost = PORTFOLIO[code]['cost']
        market = nav * shares
        profit = (nav - cost) * shares
        rate = (nav / cost - 1) * 100 if cost > 0 else 0
        total_value += market
        name = get_fund_name(code)
        pos_type = get_position_type(code)
        report += (
            f"**{code} {name} {pos_type}**\n"
            f"  持有: {shares} 份\n"
            f"  成本: {cost:.4f} → 现价: {nav:.4f}\n"
            f"  盈亏: {profit:+.2f} ({rate:+.2f}%)\n\n"
        )
    report += f"**总资产**: {total_value:.2f}\n\n"
    report += f"**🤖 投资大师评述**\n{ai_analysis}"

    send_to_feishu(report)
    print("🎉 任务完成！")
