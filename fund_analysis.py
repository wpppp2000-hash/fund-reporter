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

def get_position_instruction(code):
    """获取仓位类型的详细说明，用于prompt"""
    if code == BASE_FUND:
        return "这是底仓，长期持有，不建议大幅减仓，止损线应放宽至-15%~-20%。"
    elif code in SATELLITE_FUNDS:
        return "这是卫星仓，用于灵活配置和波段操作，可根据市场情况加减仓，止损线-8%~-10%。"
    else:
        return "这是普通仓，按正常逻辑分析，止损线-10%。"

def analyze_with_deepseek(fund_data_list, portfolio):
    """调用 DeepSeek 分析（带详细日志和空值检查）"""
    if not DEEPSEEK_API_KEY:
        return "⚠️ 未设置 DeepSeek API Key"

    # 构建持仓详情（带基金名称和仓位标记）
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

    prompt = f"""
你是我的专属基金投资顾问。我的投资偏好是：**{investment_style}**，投资期限为**{time_horizon}**年。
**特别注意：我能接受的最大回撤为10%-20%，请据此设定止损和仓位建议。**

我的持仓如下：
{funds_text}
总资产：{total_text}

{strategy_text}

请根据以上信息，提供**非常详细、可操作**的建议，要求：
1. 对每只基金分别评价，指出优点和缺点。
2. 给出明确的加减仓建议，包括具体份额或比例（如"加仓500份"或"减仓30%"）。
3. 设定明确的止损价位和止盈目标价（**严格执行上述仓位策略**）。
4. 结合当前市场环境（可参考近期A股走势），分析整体风险。
5. 回答要具体、数字量化，避免模糊的形容词。

当前日期：{datetime.now().strftime('%Y-%m-%d')}
"""

    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": 0.7
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
    print("🧠 正在调用 DeepSeek 分析...")
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
    report += f"**🤖 AI 分析**\n{ai_analysis}"

    print("📨 推送到飞书...")
    send_to_feishu(report)
    print("🎉 任务完成！")
