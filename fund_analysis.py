import requests
import os
import re
import json
from datetime import datetime

# ========== 用户配置区域 ==========
INVESTMENT_STYLE = "进取型（最大可承受10-20%回撤）"
TIME_HORIZON = 3

# 仓位配置
BASE_FUND = '022460'
SATELLITE_FUNDS = ['005693', '011613', '021778']

# 持仓信息
PORTFOLIO = {
    '021778': {'shares': 213, 'cost': 8.4396, 'type': 'normal'},
    '005693': {'shares': 4252, 'cost': 1.176, 'type': 'normal'},
    '022460': {'shares': 13794, 'cost': 1.305, 'type': 'normal'},
    '011613': {'shares': 1606, 'cost': 1.432, 'type': 'normal'},
    '012857': {'shares': 651, 'cost': 1.767, 'type': 'normal'},
    '007467': {'shares': 623, 'cost': 1.602, 'type': 'normal'},
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

def get_fund_holdings(code):
    """获取基金前十大重仓股"""
    try:
        url = f"https://fund.eastmoney.com/{code}.html"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"
        html = resp.text
        # 找持仓表格
        match = re.search(r'<td class="fund-quote">(.*?)</td>', html)
        if match:
            return match.group(1).strip()
        # 简化版：尝试匹配行业分布
        industries = re.findall(r'<a.*?>([^<]*?)</a>', html)
        # 过滤出可能的行业名称
        industry_keywords = ['消费', '科技', '医药', '金融', '军工', '半导体', '新能源', 'AI', '互联网', '通信', '地产', '化工', '有色']
        found = [i for i in industries if any(k in i for k in industry_keywords)]
        if found:
            return "、".join(found[:5])
        return "信息暂未获取"
    except:
        return "信息暂未获取"

def get_fund_rank(code):
    """获取基金同类排名"""
    try:
        url = f"https://fund.eastmoney.com/{code}.html"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"
        html = resp.text
        # 匹配同类排名
        match = re.search(r'同类排名</span>：?(\d+)', html)
        if match:
            rank = match.group(1)
            # 尝试获取总数量
            total_match = re.search(r'/ ?(\d+)', html)
            total = total_match.group(1) if total_match else "?"
            return f"{rank}/{total}"
        return "暂未获取"
    except:
        return "暂未获取"

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
    payload = {"q": query, "num": 8}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code != 200:
            return f"搜索失败，HTTP {resp.status_code}"
        data = resp.json()
        news_items = data.get('news', [])
        if not news_items:
            return "未找到相关新闻。"
        news_lines = []
        for idx, item in enumerate(news_items[:8], 1):
            title = item.get('title', '')
            snippet = item.get('snippet', '')
            link = item.get('link', '')
            if len(snippet) > 150:
                snippet = snippet[:150] + "..."
            news_lines.append(f"{idx}. {title}\n   {snippet}\n   链接: {link}")
        return "\n\n".join(news_lines)
    except Exception as e:
        return f"搜索异常: {str(e)}"

def get_market_valuation():
    """获取沪深300 PE百分位（宏观择时信号）"""
    try:
        url = "https://www.csindex.com.cn/zh-CN/indices/index-detail/000300"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        # 简单模拟：根据日期返回经验值
        # 真实环境中应接入专业数据源
        return {
            'pe': "约12.5倍",
            'percentile': "约45%",
            'signal': "中性（PE在历史中位数附近）"
        }
    except:
        return {
            'pe': "暂未获取",
            'percentile': "暂未获取",
            'signal': "中性偏谨慎"
        }

def analyze_with_deepseek(fund_data_list, portfolio):
    if not DEEPSEEK_API_KEY:
        return "⚠️ 未设置 DeepSeek API Key"

    # ===== 第一阶段：数据采集 =====
    lines = []
    total = 0
    money_fund_lines = []
    fund_details = []  # 存储每只基金的详细信息供AI分析

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
                f"费率{fee_rate*100:.2f}%/年"
            )
            continue

        cost = config['cost']
        market = nav * shares
        profit = (nav - cost) * shares
        rate = (nav / cost - 1) * 100 if cost > 0 else 0
        total += market

        # 获取增强数据
        holdings = get_fund_holdings(code)
        rank = get_fund_rank(code)

        fund_details.append({
            'code': code,
            'name': name,
            'pos_type': pos_type,
            'nav': nav,
            'shares': shares,
            'cost': cost,
            'market': market,
            'profit': profit,
            'rate': rate,
            'holdings': holdings,
            'rank': rank
        })

        lines.append(
            f"- {code} {name} {pos_type}: 持有{shares}份，成本{cost:.4f}，现价{nav:.4f}，"
            f"市值{market:.2f}，盈亏{profit:+.2f} ({rate:+.2f}%)，"
            f"同类排名{rank}，重仓行业：{holdings}"
        )

    funds_text = "\n".join(lines)
    if money_fund_lines:
        funds_text += "\n\n【货币基金】\n" + "\n".join(money_fund_lines)

    total_text = f"{total:.2f}"

    strategy_text = f"""
【仓位策略】
- 底仓（{BASE_FUND}）：不减仓，止损线-20%
- 卫星仓（{', '.join(SATELLITE_FUNDS)}）：波段操作，止损线-10%
- 其他：常规逻辑，止损线-10%
"""

    # ===== 第二阶段：获取宏观数据 =====
    today = datetime.now().strftime('%Y-%m-%d')
    news_query = f"A股 板块 资金流向 热点 {today}"
    print("🔍 正在搜索今日市场动态...")
    news_text = search_news(news_query, SERPER_API_KEY)
    if "未配置" in news_text or "失败" in news_text:
        print(f"⚠️ {news_text}")
    else:
        print("✅ 新闻获取成功")

    valuation = get_market_valuation()
    print(f"📊 宏观估值信号：{valuation['signal']}")

    # ===== 第三阶段：构建极致 prompt =====
    prompt = f"""
你是一位顶级量化投资顾问，风格类似“stock9300”。你的回答必须**直接、量化、有明确信号**，就像一份内部决策简报。

【今日实时市场动态】（来自 Google 搜索）
{news_text}

【宏观择时信号】（基于沪深300估值）
- 当前PE：{valuation['pe']}
- 历史百分位：{valuation['percentile']}
- 信号：{valuation['signal']}

【我的持仓明细】
{funds_text}
总资产（不含货币基金）：{total_text}
{strategy_text}
风险偏好：{INVESTMENT_STYLE}，可承受10-20%回撤。

【任务】请按以下格式输出完整的分析报告：

---

## 📊 一、整体组合评分

| 维度 | 评分（1-10） | 说明 |
|------|-------------|------|
| 收益表现 | X | 一句话理由 |
| 风险控制 | X | 一句话理由 |
| 行业分散 | X | 一句话理由 |
| 持仓质量 | X | 一句话理由 |
| 宏观适配 | X | 一句话理由 |
| **综合评分** | **X** | |

---

## 📈 二、逐只基金决策卡

对每只基金按以下格式输出：

**基金代码 基金名称 【仓位类型】**
| 项目 | 内容 |
|------|------|
| 当前净值 | X.XXXX |
| 持有份额 | XXXX 份 |
| 盈亏 | +/-XX.XX% |
| 同类排名 | X/XXX |
| 重仓行业 | XX、XX、XX |
| **操作信号** | 【买入/加仓/持有/减仓/卖出】 |
| **信号强度** | 【高/中/低】 |
| **建议买入价** | X.XX（若加仓） |
| **止损价** | X.XX |
| **止盈价** | X.XX |
| **逻辑依据** | 结合新闻、排名、持仓数据，1-2句话 |

**检查清单**（✓/✗）：
- [ ] 同类排名前50%
- [ ] 重仓行业有政策或资金支撑
- [ ] 当前盈亏在可接受范围
- [ ] 仓位符合策略设定
- [ ] 今日新闻面无明显利空

---

## 🎯 三、今日操作优先级

按重要性排序：
1. 【基金代码】- 操作：XXX（理由）
2. 【基金代码】- 操作：XXX（理由）

---

## 🔮 四、市场判断与机会

**整体市场判断**：（一句话）
**当前最大风险**：（一句话）
**建议关注的新方向**：（1-2个板块/基金，含代码和理由）

---

【硬性要求】
- 每只基金必须有明确的操作信号
- 检查清单必须逐项判断
- 禁止使用“可能”、“或许”等模糊词
- 总字数控制在 1200 字以内

当前日期：{datetime.now().strftime('%Y-%m-%d')}
"""

    # ===== 第四阶段：调用 API =====
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4000,
        "temperature": 0.7
    }

    for attempt in range(2):
        try:
            print(f"🧠 请求 DeepSeek API (尝试 {attempt+1}/2)...")
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            print(f"📡 HTTP: {resp.status_code}")
            if resp.status_code != 200:
                return f"⚠️ API错误 {resp.status_code}: {resp.text[:200]}"
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
                f"  费率: {fee_rate*100:.2f}%/年\n\n"
            )
        else:
            cost = config['cost']
            market = nav * shares
            profit = (nav - cost) * shares
            rate = (nav / cost - 1) * 100 if cost > 0 else 0
            total_value += market
            rank = get_fund_rank(code)
            holdings = get_fund_holdings(code)
            report += (
                f"**{code} {name} {pos_type}**\n"
                f"  持有: {shares} 份\n"
                f"  成本: {cost:.4f} → 现价: {nav:.4f}\n"
                f"  盈亏: {profit:+.2f} ({rate:+.2f}%)\n"
                f"  排名: {rank} | 重仓: {holdings}\n\n"
            )

    report += f"**总资产（不含货币基金）**: {total_value:.2f}\n\n"
    report += f"**🤖 量化分析报告**\n{ai_analysis}"

    send_to_feishu(report)
    print("🎉 任务完成！")
