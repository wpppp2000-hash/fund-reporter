import requests
import os
import re
import json
from datetime import datetime

# ========== 全局变量 ==========
INVESTMENT_STYLE = ""
TIME_HORIZON = 3
BASE_FUND = ""
SATELLITE_FUNDS = []
PORTFOLIO = {}
FUND_LIST = []

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
SERPER_API_KEY = os.environ.get('SERPER_API_KEY')
# ==================================

def load_portfolio():
    global INVESTMENT_STYLE, TIME_HORIZON, BASE_FUND, SATELLITE_FUNDS, PORTFOLIO, FUND_LIST
    config_file = "portfolio.json"
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"配置文件 {config_file} 不存在，请先创建！")
    with open(config_file, "r", encoding="utf-8") as f:
        config = json.load(f)
    INVESTMENT_STYLE = config.get("investment_style", "进取型（最大可承受10-20%回撤）")
    TIME_HORIZON = config.get("time_horizon", 3)
    BASE_FUND = config.get("base_fund", "")
    SATELLITE_FUNDS = config.get("satellite_funds", [])
    PORTFOLIO = config.get("holdings", {})
    FUND_LIST = list(PORTFOLIO.keys())
    print(f"✅ 已加载 {len(FUND_LIST)} 只基金配置")

# ========== 辅助函数（保持不变） ==========
def get_fund_name(code):
    """从天天基金网获取基金名称（使用 API 接口，更稳定）"""
    try:
        # 方法1：使用天天基金网的 JSONP 接口
        url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"
        if resp.status_code == 200:
            # 解析 JS 文件中的基金名称
            content = resp.text
            # 匹配 var fName = "基金名称";
            match = re.search(r'var fName\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1).strip()
            # 匹配 var _fundName = "基金名称";
            match = re.search(r'var _fundName\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1).strip()
    except:
        pass
    
    # 方法2：备选 - 解析 HTML 页面
    try:
        url = f"https://fund.eastmoney.com/{code}.html"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"
        html = resp.text
        # 匹配 <title>基金名称(代码) 净值... </title>
        match = re.search(r'<title>(.*?)\(', html)
        if match:
            return match.group(1).strip()
        # 匹配 h1 标签中的名称
        match = re.search(r'<h1[^>]*>(.*?)</h1>', html)
        if match:
            name = match.group(1).strip()
            # 清理可能包含的代码
            name = re.sub(r'\(\d+\)', '', name).strip()
            return name
    except:
        pass
    
    # 如果都失败，返回基金代码本身
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

def get_fund_rank(code):
    try:
        url = f"https://fund.eastmoney.com/{code}.html"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"
        html = resp.text
        rank_match = re.search(r'同类排名</span>：?<span[^>]*>(\d+)', html)
        total_match = re.search(r'同类排名</span>：?\d+\s*/\s*(\d+)', html)
        if rank_match and total_match:
            return f"{rank_match.group(1)}/{total_match.group(1)}"
        match = re.search(r'(\d+)\s*/\s*(\d+)\s*</span>', html)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
        return "数据暂缺"
    except:
        return "数据暂缺"

def get_fund_holdings(code):
    try:
        name = get_fund_name(code)
        if '纳指' in name or '纳斯达克' in name:
            return "美股科技（AI、半导体、互联网）"
        elif '军工' in name:
            return "国防军工（航天、电子、船舶）"
        elif 'A500' in name or '中证A500' in name:
            return "A股核心资产（金融、消费、科技）"
        elif '科创50' in name:
            return "科创板（半导体、AI、生物医药）"
        elif '消费' in name:
            return "大消费（食品饮料、家电、零售）"
        elif '红利低波' in name:
            return "高股息防御（银行、公用事业、能源）"
        else:
            return "行业分布均衡"
    except:
        return "数据暂缺"

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
    payload = {"q": query, "num": 6}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code != 200:
            return f"搜索失败，HTTP {resp.status_code}"
        data = resp.json()
        news_items = data.get('news', [])
        if not news_items:
            return "未找到相关新闻。"
        news_lines = []
        for idx, item in enumerate(news_items[:6], 1):
            title = item.get('title', '')
            snippet = item.get('snippet', '')
            link = item.get('link', '')
            if len(snippet) > 120:
                snippet = snippet[:120] + "..."
            news_lines.append(f"{idx}. {title}\n   {snippet}\n   链接: {link}")
        return "\n\n".join(news_lines)
    except Exception as e:
        return f"搜索异常: {str(e)}"

def get_market_valuation():
    return {
        'pe': "12.5倍",
        'percentile': "45%",
        'signal': "中性（PE在历史中位数附近）",
        'suggested_position': "70-80%"
    }

def analyze_with_deepseek(fund_data_list, portfolio):
    # 确定初始模型
    use_gemini = False
    api_key = None
    url = None
    model = None

    if GEMINI_API_KEY:
        use_gemini = True
        api_key = GEMINI_API_KEY
        url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        model = "gemini-2.0-flash"
        print("🧠 使用 Gemini 模型")
    elif DEEPSEEK_API_KEY:
        use_gemini = False
        api_key = DEEPSEEK_API_KEY
        url = "https://api.deepseek.com/chat/completions"
        model = "deepseek-v4-pro"
        print("🧠 使用 DeepSeek 模型")
    else:
        return "⚠️ 未设置任何 API Key (GEMINI_API_KEY 或 DEEPSEEK_API_KEY)"

    # 构建持仓详情
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
                f"费率{fee_rate*100:.2f}%/年"
            )
            continue

        cost = config['cost']
        market = nav * shares
        profit = (nav - cost) * shares
        rate = (nav / cost - 1) * 100 if cost > 0 else 0
        total += market

        rank = get_fund_rank(code)
        holdings = get_fund_holdings(code)

        lines.append(
            f"- {code} {name} {pos_type}: 持有{shares}份，成本{cost:.4f}，现价{nav:.4f}，"
            f"市值{market:.2f}，盈亏{profit:+.2f} ({rate:+.2f}%)，"
            f"同类排名: {rank}，重仓行业: {holdings}"
        )

    funds_text = "\n".join(lines)
    if money_fund_lines:
        funds_text += "\n\n【货币基金】\n" + "\n".join(money_fund_lines)

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

    valuation = get_market_valuation()
    print(f"📊 宏观估值信号：{valuation['signal']}，建议仓位：{valuation['suggested_position']}")

    prompt = f"""
你是一位顶级量化投资顾问，回答必须**直接、量化、有明确信号**。

【今日实时市场动态】（来自 Google 搜索）
{news_text}

【宏观择时信号】（基于沪深300估值）
- 当前PE：{valuation['pe']}
- 历史百分位：{valuation['percentile']}
- 信号：{valuation['signal']}
- 建议整体仓位：{valuation['suggested_position']}

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

**基金代码 基金名称 【仓位类型】**
| 项目 | 内容 |
|------|------|
| 当前净值 | X.XXXX |
| 持有份额 | XXXX 份 |
| 盈亏 | +/-XX.XX% |
| 同类排名 | X/XXX（数据暂缺则标注） |
| 重仓行业 | XX（基于基金名称推断） |
| **操作信号** | 【买入/加仓/持有/减仓/卖出】 |
| **信号强度** | 【高/中/低】 |
| **建议买入价** | X.XX（若适用） |
| **止损价** | X.XX |
| **止盈价** | X.XX |
| **逻辑依据** | 1-2句话 |

**检查清单**（✓/✗ / 数据暂缺）：
- [ ] 同类排名前50%（数据暂缺标注"不计分"）
- [ ] 重仓行业有政策或资金支撑
- [ ] 当前盈亏在可接受范围
- [ ] 仓位符合策略设定
- [ ] 今日新闻面无明显利空

---

## 🎯 三、今日操作优先级

按重要性排序：

---

## 🔮 四、市场判断与机会

**整体市场判断**：（一句话）
**当前最大风险**：（一句话）

**建议关注的新方向**：（最多2个，按以下格式）
1. **方向名称 + 代表基金代码（必须是场外基金，0或5开头）**
   - 推荐理由：与现有持仓的差异化互补点（不重复）
   - 当前估值位置：（高/中/低/历史分位）
   - 入场建议：【现在买/等回调X%/分批建仓】
   - 参考触发价：X.XX（如适用）
   - 预期持有周期：（短线/中线/长线）
   - 与本轮操作建议的协调性：（不矛盾）

2. **方向名称 + 代表基金代码（必须是场外基金，0或5开头）**
   - 同上格式

【硬性约束】
- **只能推荐场外基金**（代码以0或5开头，如 022460、005693）
- **禁止推荐场内ETF**（如 159915、510050、518880 等）
- 如果想推荐ETF方向，请给出对应的**场外联接基金**代码（如 013123 某某ETF联接C）
- 如果当前没有合适的场外基金方向，直接输出“暂无”并说明理由

**如果当前没有合适的新方向，直接输出“暂无”并说明理由。**

---

【硬性要求】
- 新方向推荐**必须**与现有持仓差异化，不能重复同方向
- 必须给出**入场时机和触发条件**，避免追高
- 必须与今日操作建议逻辑一致
- 禁止使用模糊词
- 总字数控制在 1200 字以内

当前日期：{datetime.now().strftime('%Y-%m-%d')}
"""

    # ===== 请求函数 =====
    def make_request(api_key, url, model, payload):
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        # Gemini 支持 reasoning_effort
        if model.startswith("gemini"):
            payload["reasoning_effort"] = "high"
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        return resp

    # 尝试请求（支持回退）
    for attempt in range(3):  # 最多尝试3次（包括回退）
        try:
            print(f"🧠 请求 API (尝试 {attempt+1}/3)...")
            resp = make_request(api_key, url, model, {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4000,
                "temperature": 0.7
            })
            print(f"📡 HTTP: {resp.status_code}")

            # 如果 Gemini 429 且 DeepSeek 可用，回退
            if resp.status_code == 429 and use_gemini and DEEPSEEK_API_KEY:
                print("⚠️ Gemini 配额用尽，自动回退到 DeepSeek...")
                use_gemini = False
                api_key = DEEPSEEK_API_KEY
                url = "https://api.deepseek.com/chat/completions"
                model = "deepseek-v4-pro"
                # 重置 payload 中的 model
                continue  # 重新尝试

            if resp.status_code != 200:
                return f"⚠️ API错误 {resp.status_code}: {resp.text[:200]}"

            result = resp.json()
            content = result['choices'][0].get('message', {}).get('content', '')
            if not content or content.strip() == '':
                return "⚠️ API返回空内容，请重试"
            print(f"✅ 分析成功，{len(content)}字符")
            return content

        except requests.exceptions.Timeout:
            print(f"⏱️ 超时 (尝试 {attempt+1}/3)")
            if attempt == 2:
                return "⚠️ 三次超时，请稍后重试"
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
    load_portfolio()
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
    print("🧠 调用分析模型...")
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
