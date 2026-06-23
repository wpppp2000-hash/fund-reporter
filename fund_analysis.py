import requests
import os
import re
import json
from datetime import datetime, timedelta
import akshare as ak

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

HISTORY_DIR = "history"
# ==================================

def ensure_history_dir():
    if not os.path.exists(HISTORY_DIR):
        os.makedirs(HISTORY_DIR)
        print(f"✅ 已创建历史目录: {HISTORY_DIR}")

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

# ========== 交易日判断 ==========
def is_trading_day():
    """判断今天是否是A股交易日 - 混合方案：akshare + 硬编码"""
    today = datetime.now().strftime('%Y-%m-%d')
    weekday = datetime.now().weekday()

    # ====== 第一步：先排除周末（周六、周日一定不开盘） ======
    if weekday >= 5:
        print(f"📅 非交易日 ({today}，周末)")
        return False

    # ====== 第二步：硬编码 2026 年 A 股非交易日 ======
    holidays_2026 = {
        # 元旦
        "2026-01-01", "2026-01-02",
        # 春节（2月16日-20日）
        "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
        # 清明节
        "2026-04-06",
        # 劳动节
        "2026-05-01", "2026-05-04", "2026-05-05",
        # 端午节（6月19日-21日）← 修正
        "2026-06-19", "2026-06-20", "2026-06-21",
        # 中秋节 + 国庆节（10月1日-7日）
        "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07",
    }

    work_weekends_2026 = {
        "2026-01-04",
        "2026-02-14", "2026-02-15",
        "2026-04-11", "2026-04-12",
        "2026-05-09", "2026-05-10",
        "2026-06-20", "2026-06-21",
        "2026-09-26", "2026-10-10",
    }

    if today in holidays_2026:
        print(f"📅 非交易日 ({today}，节假日)")
        return False

    if today in work_weekends_2026:
        print(f"📅 交易日 ({today}，调休补班)")
        return True

    # ====== 第三步：用 akshare 验证 ======
    try:
        trade_cal = ak.tool_trade_date_hist_sina()
        if trade_cal is not None and not trade_cal.empty:
            dates = trade_cal['trade_date'].tolist()
            if today in dates:
                print(f"📅 交易日(akshare验证): {today}")
                return True
    except Exception as e:
        print(f"⚠️ akshare 验证失败: {e}")

    # ====== 第四步：硬编码判定 ======
    print(f"📅 交易日 (硬编码判定): {today}")
    return True

# ========== 历史数据读写 ==========
def load_nav_history(days=5):
    nav_file = os.path.join(HISTORY_DIR, "nav.json")
    if not os.path.exists(nav_file):
        return {}
    with open(nav_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    sorted_dates = sorted(data.keys(), reverse=True)
    recent_dates = sorted_dates[:days]
    return {d: data[d] for d in recent_dates}

def load_analysis_history(days=3):
    analysis_file = os.path.join(HISTORY_DIR, "analysis.json")
    if not os.path.exists(analysis_file):
        return {}
    with open(analysis_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    sorted_dates = sorted(data.keys(), reverse=True)
    recent_dates = sorted_dates[:days]
    return {d: data[d] for d in recent_dates}

def save_nav_history(date, nav_data):
    nav_file = os.path.join(HISTORY_DIR, "nav.json")
    data = {}
    if os.path.exists(nav_file):
        with open(nav_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    data[date] = nav_data
    with open(nav_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 已保存净值历史 ({len(nav_data)} 只基金)")

def save_analysis_history(date, score, summary, suggestions):
    analysis_file = os.path.join(HISTORY_DIR, "analysis.json")
    data = {}
    if os.path.exists(analysis_file):
        with open(analysis_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    data[date] = {
        "score": score,
        "summary": summary,
        "suggestions": suggestions
    }
    with open(analysis_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 已保存分析摘要 (评分: {score})")

# ========== 辅助函数 ==========
def get_fund_name(code):
    try:
        url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"
        if resp.status_code == 200:
            content = resp.text
            match = re.search(r'var fName\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1).strip()
            match = re.search(r'var _fundName\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1).strip()
    except:
        pass
    try:
        url = f"https://fund.eastmoney.com/{code}.html"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"
        html = resp.text
        match = re.search(r'<title>(.*?)\(', html)
        if match:
            return match.group(1).strip()
        match = re.search(r'<h1[^>]*>(.*?)</h1>', html)
        if match:
            name = match.group(1).strip()
            name = re.sub(r'\(\d+\)', '', name).strip()
            return name
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

def analyze_with_deepseek(fund_data_list, portfolio, nav_history, analysis_history):
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
        return "⚠️ 未设置任何 API Key", None

    lines = []
    total = 0
    money_fund_lines = []
    nav_record = {}

    for item in fund_data_list:
        code = item['code']
        nav = item['nav']
        config = portfolio[code]
        shares = config['shares']
        fund_type = config.get('type', 'normal')
        name = get_fund_name(code)
        pos_type = get_position_type(code)
        nav_record[code] = nav

        if fund_type == 'money':
            fee_rate = config.get('fee_rate', 0.0033)
            money_fund_lines.append(
                f"- {code} {name} {pos_type} 【货币基金】: 持有{shares}份，费率{fee_rate*100:.2f}%/年"
            )
            continue

        cost = config['cost']
        market = nav * shares
        profit = (nav - cost) * shares
        rate = (nav / cost - 1) * 100 if cost > 0 else 0
        total += market
        holdings = get_fund_holdings(code)
        lines.append(
            f"- {code} {name} {pos_type}: 持有{shares}份，成本{cost:.4f}，现价{nav:.4f}，"
            f"市值{market:.2f}，盈亏{profit:+.2f} ({rate:+.2f}%)，重仓行业: {holdings}"
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
    news_query = f"A股 热点 板块 资金流向 政策 {today}"
    print("🔍 正在搜索今日市场动态...")
    news_text = search_news(news_query, SERPER_API_KEY)
    if "未配置" in news_text or "失败" in news_text:
        print(f"⚠️ {news_text}")
    else:
        print("✅ 新闻获取成功")

    valuation = get_market_valuation()
    print(f"📊 宏观估值信号：{valuation['signal']}，建议仓位：{valuation['suggested_position']}")

    history_text = ""
    if nav_history:
        history_text += "\n【最近5天净值趋势（供参考）】\n"
        sorted_dates = sorted(nav_history.keys())
        for d in sorted_dates[-5:]:
            day_nav = nav_history[d]
            trend_line = f"{d}: "
            for code in sorted(day_nav.keys()):
                if code in FUND_LIST:
                    trend_line += f"{code}={day_nav[code]:.4f} "
            history_text += trend_line + "\n"
    
    if analysis_history:
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        if yesterday in analysis_history:
            y = analysis_history[yesterday]
            history_text += f"\n【昨日分析摘要（{yesterday}）】\n"
            history_text += f"评分: {y.get('score', 'N/A')}\n"
            history_text += f"诊断: {y.get('summary', '')}\n"
            history_text += f"操作建议: {y.get('suggestions', '')}\n"
        else:
            if analysis_history:
                last_date = max(analysis_history.keys())
                y = analysis_history[last_date]
                history_text += f"\n【最近分析摘要（{last_date}）】\n"
                history_text += f"评分: {y.get('score', 'N/A')}\n"
                history_text += f"诊断: {y.get('summary', '')}\n"
                history_text += f"操作建议: {y.get('suggestions', '')}\n"

    prompt = f"""
你是顶级量化投资顾问，回答必须**直接、量化、明确信号**。不要输出推理过程，只输出结论。

【内部参考】你已综合分析了市场状态、时政新闻、资金流向、估值水位，完成了深度推演和决策自检。现在只输出结果。

【我的持仓】
{funds_text}
总资产：{total_text}
{strategy_text}
风险偏好：{INVESTMENT_STYLE}

{history_text}

---

📈 基金持仓日报 - {today}

## 一、今日操作清单（核心）

按重要性排列，只列今天必须执行的操作：

| 优先级 | 基金 | 操作 | 份额/比例 | 理由（一句话） |
|--------|------|------|-----------|---------------|
| 1 | 代码 基金简称 | 买入/加仓/持有/减仓/卖出 | X% 或 X份 | 一句话理由 |
| ... | ... | ... | ... | ... |

如果没有任何操作需要执行，直接输出：今日无操作，继续持有全部仓位。

---

## 二、组合诊断（一句话 + 评分）

**综合评分**：X.X/10
**一句话诊断**：XXX

| 维度 | 评分 |
|------|------|
| 收益表现 | X |
| 风险控制 | X |
| 行业分散 | X |
| 持仓质量 | X |
| 宏观适配 | X |

---

## 三、可关注方向（最多1个）

**只推荐你当前未持有的基金。** 如果所有看好的方向都已持有，直接输出：暂无。

方向名称 + 基金代码（场外基金，0或5开头）
- 理由：一句话
- 入场建议：现在买/等回调X%/分批建仓
- 参考触发价：X.XX

【硬性约束】
- 可关注方向必须是你当前**未持有**的基金
- 如果已持有，请直接输出"暂无"
- 禁止推荐场内ETF

---

【硬性要求】
- 操作清单中的基金必须使用正确的基金代码
- 操作必须是【买入/加仓/持有/减仓/卖出】中的一项
- 每个操作必须有具体份额或比例
- 总字数控制在600字以内
"""

    def make_request(api_key, url, model, payload):
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        if model.startswith("gemini"):
            payload["reasoning_effort"] = "high"
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        return resp

    for attempt in range(3):
        try:
            print(f"🧠 请求 API (尝试 {attempt+1}/3)...")
            resp = make_request(api_key, url, model, {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 3000,
                "temperature": 0.7
            })
            print(f"📡 HTTP: {resp.status_code}")

            if resp.status_code == 429 and use_gemini and DEEPSEEK_API_KEY:
                print("⚠️ Gemini 配额用尽，自动回退到 DeepSeek...")
                use_gemini = False
                api_key = DEEPSEEK_API_KEY
                url = "https://api.deepseek.com/chat/completions"
                model = "deepseek-v4-pro"
                continue

            if resp.status_code != 200:
                return f"⚠️ API错误 {resp.status_code}: {resp.text[:200]}", None

            result = resp.json()
            content = result['choices'][0].get('message', {}).get('content', '')
            if not content or content.strip() == '':
                return "⚠️ API返回空内容，请重试", None
            print(f"✅ 分析成功，{len(content)}字符")
            return content, nav_record

        except requests.exceptions.Timeout:
            print(f"⏱️ 超时 (尝试 {attempt+1}/3)")
            if attempt == 2:
                return "⚠️ 三次超时，请稍后重试", None
            continue
        except Exception as e:
            return f"⚠️ 分析失败: {e}", None

    return "⚠️ 未知错误", None

# ========== 增强版飞书推送 ==========
def send_to_feishu(message):
    if not FEISHU_WEBHOOK:
        print("❌ 未配置 FEISHU_WEBHOOK 环境变量")
        return
    
    print(f"📨 正在推送消息到飞书...")
    print(f"📝 消息长度: {len(message)} 字符")
    
    data = {"msg_type": "text", "content": {"text": message}}
    try:
        r = requests.post(FEISHU_WEBHOOK, json=data, timeout=10)
        print(f"📡 HTTP 状态码: {r.status_code}")
        print(f"📡 响应内容: {r.text}")
        
        if r.status_code == 200:
            try:
                resp_json = r.json()
                if resp_json.get('code') == 0:
                    print("✅ 飞书推送成功")
                else:
                    print(f"❌ 飞书返回错误码: {resp_json.get('code')}, 消息: {resp_json.get('msg')}")
            except:
                print("⚠️ 无法解析飞书响应")
        else:
            print(f"❌ 推送失败，HTTP {r.status_code}")
    except requests.exceptions.Timeout:
        print("❌ 飞书请求超时")
    except Exception as e:
        print(f"❌ 飞书推送异常: {e}")
# =====================================

if __name__ == "__main__":
    # 1. 创建历史目录
    ensure_history_dir()

    # 2. 交易日判断
    if not is_trading_day():
        print("📅 今日非交易日，跳过分析推送")
        exit(0)

    # 3. 加载配置
    load_portfolio()

    # 4. 加载历史数据
    nav_history = load_nav_history(days=5)
    analysis_history = load_analysis_history(days=3)
    print(f"📚 加载了 {len(nav_history)} 天净值历史，{len(analysis_history)} 天分析摘要")

    # 5. 获取基金数据
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

    # 6. 调用 AI 分析
    print(f"📊 成功获取 {len(valid_data)} 只基金")
    print("🧠 调用分析模型...")
    ai_analysis, nav_record = analyze_with_deepseek(valid_data, PORTFOLIO, nav_history, analysis_history)

    # 7. 构建并发送飞书报告
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
            holdings = get_fund_holdings(code)
            report += (
                f"**{code} {name} {pos_type}**\n"
                f"  持有: {shares} 份\n"
                f"  成本: {cost:.4f} → 现价: {nav:.4f}\n"
                f"  盈亏: {profit:+.2f} ({rate:+.2f}%)\n"
                f"  重仓: {holdings}\n\n"
            )

    report += f"**总资产（不含货币基金）**: {total_value:.2f}\n\n"
    report += f"**🤖 量化分析报告**\n{ai_analysis}"

    print("📨 正在发送飞书推送...")
    send_to_feishu(report)

    # 8. 保存历史记录
    today_str = datetime.now().strftime('%Y-%m-%d')
    if nav_record:
        save_nav_history(today_str, nav_record)

    # 9. 从 AI 分析中提取评分和摘要
    score_match = re.search(r'\*\*综合评分\*\*[：:]\s*([\d.]+)', ai_analysis)
    score = score_match.group(1) if score_match else "N/A"
    summary_match = re.search(r'\*\*一句话诊断\*\*[：:]\s*(.+?)(?:\n|$)', ai_analysis)
    summary = summary_match.group(1) if summary_match else ""
    suggestions = ""
    suggestion_section = re.search(r'## 一、今日操作清单.*?\n(.*?)(?=\n##|\Z)', ai_analysis, re.DOTALL)
    if suggestion_section:
        suggestions = suggestion_section.group(1).strip()
    save_analysis_history(today_str, score, summary, suggestions)

    print("🎉 任务完成！")
