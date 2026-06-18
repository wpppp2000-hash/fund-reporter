import requests
import os
import re
from datetime import datetime

# ========== 用户配置区域 ==========
# 投资偏好（影响AI建议风格）
INVESTMENT_STYLE = "进取型（最大可承受10-20%回撤）"
TIME_HORIZON = 3             # 投资期限（年）

# 仓位配置
BASE_FUND = '022460'                      # 底仓（核心资产，长期持有）
SATELLITE_FUNDS = ['005693', '011613', '021778']    # 卫星仓（灵活配置，波段操作）
# 未标记的基金为普通仓

# 持仓信息：{'基金代码': {'shares': 持有份额, 'cost': 成本单价}}
PORTFOLIO = {
    '021778': {'shares': 213, 'cost': 8.4396},
    '005693': {'shares': 4252, 'cost': 1.176},
    '022460': {'shares': 13794, 'cost': 1.305},
    '011613': {'shares': 1606, 'cost': 1.432},
    '012857': {'shares': 651, 'cost': 1.767},
    '007467': {'shares': 623, 'cost': 1.602},
}
FUND_LIST = list(PORTFOLIO.keys())

# 密钥（从 GitHub Secrets 读取）
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
# ==================================

def get_fund_name(code):
    """从东方财富获取基金名称"""
    try:
        url = f"https://fund.eastmoney.com/{code}.html"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"
        html = resp.text
        match = re.search(r'<title>(.*?)基金净值', html)
        if match:
            name = match.group(1).strip()
            return name
        match = re.search(r'<h1 class="fundName">(.*?)</h1>', html)
        if match:
            name = match.group(1).strip()
            return name
    except Exception as e:
        print(f"⚠️ 获取基金名称 {code} 失败: {e}")
    return code

def get_fund_nav_sina(code):
    """从新浪财经获取基金净值"""
    try:
        url = f"https://hq.sinajs.cn/list=f_{code}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://finance.sina.com.cn/"
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "gbk"
        data = resp.text
        if "var hq_str_f_" in data:
            parts = data.split('"')[1].split(',')
            if len(parts) >= 5:
                nav = float(parts[1])
                date = parts[3]
                return {'code': code, 'nav': nav, 'date': date}
            else:
                print(f"⚠️ 新浪返回数据格式异常: {data[:100]}")
    except Exception as e:
        print(f"⚠️ 新浪获取 {code} 失败: {e}")
    return None

def get_fund_nav_eastmoney(code):
    """从东方财富官网获取基金净值（备用）"""
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
        else:
            print(f"⚠️ 东方财富未找到净值: {code}")
    except Exception as e:
        print(f"⚠️ 东方财富获取 {code} 失败: {e}")
    return None

def get_position_type(code):
    """获取基金仓位类型标记"""
    if code == BASE_FUND:
        return "【底仓】"
    elif code in SATELLITE_FUNDS:
        return "【卫星仓】"
    else:
        return ""

def analyze_with_deepseek(fund_data_list, portfolio):
    """
    调用 DeepSeek API，以投资大师（巴菲特/索罗斯/彼得·林奇综合风格）进行分析。
    返回拟人化的投资建议。
    """
    if not DEEPSEEK_API_KEY:
        return "⚠️ 未设置 DeepSeek API Key"

    # 构建持仓详情
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
    investment_style = INVESTMENT_STYLE
    time_horizon = TIME_HORIZON

    # 构建仓位策略说明
    strategy_text = f"""
【仓位策略】
- 底仓（{BASE_FUND}）：核心资产，长期持有，不减仓，止损线-20%。
- 卫星仓（{', '.join(SATELLITE_FUNDS)}）：灵活配置，波段操作，止损线-10%。
- 其他普通仓：按常规逻辑分析，止损线-10%。
"""

    # ===================== 关键修改：大师风格的 prompt =====================
    prompt = f"""
你是一位纵横华尔街三十年的投资大师，曾亲历多次牛熊转换，既深谙巴菲特的价值投资哲学，也精通索罗斯的反射性理论，更懂得彼得·林奇从生活中发现成长股的智慧。
现在，你受邀为一位私人投资者（我）提供持仓诊断和操作建议。

【我的投资画像】
- 风险偏好：{investment_style}（可承受10-20%回撤）
- 投资期限：{time_horizon}年
- 仓位策略：{strategy_text}

【当前持仓明细】
{funds_text}
总资产：{total_text}

【今日市场背景】（请结合近期A股走势，如科技、军工、消费等板块表现）

请你以第一人称“我”的口吻，写一份**极具个人风格、见解独到、语气自信**的投资评述。要求：
1. **开场白**：用一句经典投资格言或市场洞察引入（如“在别人恐惧时贪婪……”）。
2. **逐一评价每只基金**：指出其本质（是“护城河”还是“周期性”），给出明确的定性判断（“这是好东西”或“这个需要警惕”）。
3. **具体操作指令**：对每只基金明确说出“加仓”、“减仓”或“持有”，并给出具体份额/比例（例如“再买500份”或“卖掉三分之一”），同时设定清晰的止损价和止盈目标。
4. **宏观风险提示**：结合当前宏观经济或地缘政治，指出潜在黑天鹅，并给出应对预案。
5. **结尾**：用一句富有哲理的投资心得收尾，增强信任感。

**语言风格要求**：
- 口语化、有温度，像一位长者在对晚辈传授经验。
- 多用比喻和类比（如“这只基金就像一艘坚固的军舰”）。
- 敢于说“不”，敢于亮出鲜明观点。
- 适当引用经典投资书籍或名人名言（但不要过度）。

回答控制在800字以内，既要高屋建瓴，也要落到实处。
当前日期：{datetime.now().strftime('%Y-%m-%d')}
"""
    # =====================================================================

    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4000,
        "temperature": 0.8,      # 稍微提高温度，让语言更生动
        "enable_search": True    # 联网获取最新市场信息
    }

    for attempt in range(2):
        try:
            print(f"🧠 正在请求 DeepSeek API (尝试 {attempt+1}/2)...")
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            print(f"📡 HTTP 状态码: {resp.status_code}")
            if resp.status_code != 200:
                print(f"❌ 请求失败，响应内容: {resp.text[:200]}")
                return f"⚠️ API 返回错误 {resp.status_code}: {resp.text[:100]}"
            result = resp.json()
            if 'choices' not in result or not result['choices']:
                print(f"❌ API 响应格式异常: {result}")
                return "⚠️ API 响应格式异常，未找到 choices 字段"
            content = result['choices'][0].get('message', {}).get('content', '')
            if not content or content.strip() == '':
                print("⚠️ API 返回了空内容")
                finish_reason = result['choices'][0].get('finish_reason')
                if finish_reason == 'length':
                    return "⚠️ 分析内容过长被截断，请减少持仓数量或调整提示词"
                else:
                    return "⚠️ AI 返回了空内容，请稍后重试"
            print(f"✅ 分析成功，内容长度: {len(content)} 字符")
            return content
        except requests.exceptions.Timeout:
            print(f"⏱️ DeepSeek 超时 (尝试 {attempt+1}/2)")
            if attempt == 1:
                return "⚠️ DeepSeek API 两次超时，请稍后重试。"
            continue
        except Exception as e:
            print(f"❌ 请求异常: {e}")
            return f"⚠️ AI分析失败: {e}"
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
            print(f"❌ 飞书推送失败: {r.status_code} {r.text}")
    except Exception as e:
        print(f"❌ 飞书推送异常: {e}")

if __name__ == "__main__":
    print("🚀 开始获取基金数据...")
    print(f"📌 基金列表: {FUND_LIST}")

    valid_data = []
    for code in FUND_LIST:
        print(f"🔍 尝试获取 {code}...")
        data = get_fund_nav_sina(code)
        if not data:
            print(f"  新浪失败，尝试东方财富...")
            data = get_fund_nav_eastmoney(code)
        if data:
            valid_data.append(data)
            print(f"✅ {code} 成功: 净值 {data['nav']} (日期 {data['date']})")
        else:
            print(f"❌ {code} 所有方法均失败")

    if not valid_data:
        error_msg = f"❌ 所有基金数据获取失败 (共 {len(FUND_LIST)} 只)。\n请检查基金代码是否正确。"
        send_to_feishu(error_msg)
        print(error_msg)
        exit(1)

    print(f"📊 成功获取 {len(valid_data)} 只基金数据")
    print("🧠 正在调用 DeepSeek 分析（大师风格）...")
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

    print("📨 推送到飞书...")
    send_to_feishu(report)
    print("🎉 任务完成！")
