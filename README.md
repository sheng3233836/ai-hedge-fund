# AI Hedge Fund

[English](#english-version) | **中文说明见下方 ↓**

---

## 🇨🇳 中文说明

### 项目简介

这是一个基于 AI 的对冲基金概念验证项目，使用多个 AI 智能体协作做出投资分析与交易决策。本项目**仅供学习和研究使用**，不构成任何实际的投资建议。

> ✅ **本 Fork 版本已新增对 A 股（沪深北交所）的支持**，输入 6 位股票数字代码即可分析，数据来源为 AKShare，分析结果可选择中文输出。

---

### 🇨🇳 A 股支持说明

| 功能 | 说明 |
|------|------|
| **行情数据** | 日线 OHLCV（前复权），来源：东方财富 |
| **估值指标** | PE(TTM)、PB、总市值 |
| **盈利能力** | ROE、净利率、毛利率、EPS、每股净资产 |
| **财务健康** | ROA、营业利润率、资产负债率、流动比率 |
| **成长指标** | 营业收入增长率、净利润增长率 |
| **财务报表** | 资产负债表、利润表、现金流量表逐期明细 |
| **个股新闻** | 标题、来源、发布时间 |
| **中文输出** | A 股代码自动触发中文推理，也可 `--zh` / `--en` 手动切换 |

**支持的市场代码格式**

| 交易所 | 代码范围 | 示例 |
|--------|---------|------|
| 上交所（主板/科创板） | 6xxxxx / 688xxx | 600519（贵州茅台）、688981（中芯国际） |
| 深交所（主板/创业板） | 0xxxxx / 3xxxxx | 000858（五粮液）、300750（宁德时代） |
| 北交所 | 43xxxx / 8xxxxx | 838012（曙光数创） |

**使用示例**

```bash
# 分析 A 股（自动中文输出）
poetry run python src/main.py --tickers 600519,000858,300750

# 混合 A 股 + 美股，强制中文
poetry run python src/main.py --tickers 600519,AAPL --zh

# 第三方 OpenAI 兼容平台（配置 .env 中 CUSTOM_LLM_* 后可用）
poetry run python src/main.py --tickers 600519 --model your-model-name
```

---

### 🧠 19 位分析师一览与分组

系统共有 **19 位分析师 Agent**，按投资风格分为以下 5 组：

#### 📌 A 组 · 价值投资派（Value Investing）

> 核心逻辑：寻找被市场低估、具有安全边际的优质公司，长期持有。

| 分析师 | 绰号 | 核心特点 |
|--------|------|---------|
| **Warren Buffett** | 奥马哈神谕 | 护城河 + 合理价格 + 长期持有；ROE、自由现金流是核心指标 |
| **Charlie Munger** | 理性思考者 | 只买"好生意"；多元思维模型；拒绝平庸资产 |
| **Ben Graham** | 价值投资之父 | 安全边际至上；严格筛选 P/B、P/E；偏爱净资产折价资产 |
| **Mohnish Pabrai** | Dhandho 投资者 | "低风险、高回报"；克隆巴菲特框架；极度集中持仓 |
| **Michael Burry** | 大空头逆向者 | 深度价值挖掘；善用逆向思维；对高负债/高估值做空 |

#### 📌 B 组 · 成长投资派（Growth Investing）

> 核心逻辑：聚焦高成长赛道与创新公司，接受较高估值换取未来回报。

| 分析师 | 绰号 | 核心特点 |
|--------|------|---------|
| **Cathie Wood** | 成长投资女王 | 颠覆性创新；5 年以上视野；AI、基因、新能源等主题 |
| **Phil Fisher** | 深度调研者 | 深入管理层调研（scuttlebutt）；重视 R&D 与创新能力 |
| **Peter Lynch** | 十倍股猎手 | "买你熟悉的"；PEG 估值法；偏爱生活中能感知的好公司 |
| **Growth Analyst** | 成长量化分析师 | 系统量化成长趋势与估值匹配度 |

#### 📌 C 组 · 估值分析派（Valuation Analysis）

> 核心逻辑：用模型计算内在价值，以数字为准绳做出决策。

| 分析师 | 绰号 | 核心特点 |
|--------|------|---------|
| **Aswath Damodaran** | 估值教父 | DCF + 相对估值双轨；故事与数字并重；适配任何行业 |
| **Valuation Analyst** | 估值量化分析师 | 多模型综合计算内在价值；输出结构化信号 |

#### 📌 D 组 · 宏观 / 风险派（Macro & Risk）

> 核心逻辑：自上而下看经济周期与政策，保护组合、捕捉宏观机会。

| 分析师 | 绰号 | 核心特点 |
|--------|------|---------|
| **Stanley Druckenmiller** | 宏观传奇 | 货币、大宗、利率大仓位押注；擅长把握经济拐点 |
| **Nassim Taleb** | 黑天鹅守护者 | 尾部风险优先；杠铃策略；反脆弱；极度厌恶脆性资产 |
| **Rakesh Jhunjhunwala** | 印度大牛 | 新兴市场成长；宏观趋势 + 行业景气度；适合发展中国家市场 |

#### 📌 E 组 · 量化 / 系统分析派（Quant & Sentiment）

> 核心逻辑：基于数据与市场信号，不依赖主观判断，提供客观参照。

| 分析师 | 绰号 | 核心特点 |
|--------|------|---------|
| **Technical Analyst** | 技术面分析师 | EMA、RSI、布林带、ADX、Hurst 指数等多维技术信号 |
| **Fundamentals Analyst** | 基本面分析师 | 盈利 / 成长 / 健康 / 估值四维量化评分 |
| **News Sentiment Analyst** | 新闻情绪分析师 | 实时新闻情感分析，捕捉舆论拐点 |
| **Sentiment Analyst** | 市场情绪分析师 | 内部人交易、市场情绪行为分析 |

---

### 🎯 A 股分析推荐组合

#### 🏆 组合一：白马蓝筹精选（消费 / 医药 / 金融）

```
--analysts warren_buffett,charlie_munger,ben_graham,fundamentals_analyst,valuation_analyst
```

**适用场景**：茅台、平安、招商银行、恒瑞医药等高护城河蓝筹股  
**逻辑**：A 股蓝筹长期处于国际低估状态，价值派三剑客可精准识别安全边际，配合基本面量化做交叉验证。

---

#### 🚀 组合二：科技成长精选（科创板 / 创业板）

```
--analysts cathie_wood,peter_lynch,phil_fisher,technical_analyst,growth_analyst
```

**适用场景**：宁德时代、中芯国际、迈瑞医疗、金山办公等成长龙头  
**逻辑**：科创板个股估值高但赛道清晰，成长派分析师看得懂技术壁垒，技术分析辅助把握进场时机。

---

#### ⚖️ 组合三：均衡全面（通用推荐）

```
--analysts warren_buffett,aswath_damodaran,rakesh_jhunjhunwala,technical_analyst,fundamentals_analyst,news_sentiment_analyst
```

**适用场景**：不确定板块时的默认分析组合  
**逻辑**：估值（巴菲特/达摩达兰）+ 新兴市场经验（Jhunjhunwala 对政策驱动市场最有经验）+ 技术面 + 基本面 + 新闻，四个维度交叉验证，最适合 A 股政策敏感的市场特征。

---

#### 🛡️ 组合四：防御风控（震荡市 / 熊市）

```
--analysts nassim_taleb,ben_graham,stanley_druckenmiller,technical_analyst,sentiment_analyst
```

**适用场景**：市场波动剧烈、宏观不确定性高时  
**逻辑**：塔勒布的尾部风险框架 + 格雷厄姆的底价安全网 + 德鲁肯米勒的宏观判断，三者共识才建仓，有效规避 A 股暴跌风险。

---

### ⚙️ 快速开始（A 股版）

**1. 安装依赖**
```bash
git clone https://github.com/your-fork/ai-hedge-fund.git
cd ai-hedge-fund
poetry install
```

**2. 配置 `.env`**
```bash
cp .env.example .env
# 编辑 .env，至少填写一个 LLM 的 API Key
# A 股数据来源 AKShare，无需额外 API Key
```

**3. 运行分析**
```bash
# 白马蓝筹组合分析贵州茅台
poetry run python src/main.py \
  --tickers 600519 \
  --analysts warren_buffett,charlie_munger,ben_graham,fundamentals_analyst,valuation_analyst \
  --start-date 2025-01-01 \
  --end-date 2026-04-13 \
  --show-reasoning

# 使用第三方平台（如硅基流动）
# 先在 .env 设置 CUSTOM_LLM_API_KEY / BASE_URL / MODEL
poetry run python src/main.py --tickers 600519,300750 --model your-model-name --zh
```

---

<a name="english-version"></a>

# AI Hedge Fund

This is a proof of concept for an AI-powered hedge fund.  The goal of this project is to explore the use of AI to make trading decisions.  This project is for **educational** purposes only and is not intended for real trading or investment.

This system employs several agents working together:

1. Aswath Damodaran Agent - The Dean of Valuation, focuses on story, numbers, and disciplined valuation
2. Ben Graham Agent - The godfather of value investing, only buys hidden gems with a margin of safety
3. Bill Ackman Agent - An activist investor, takes bold positions and pushes for change
4. Cathie Wood Agent - The queen of growth investing, believes in the power of innovation and disruption
5. Charlie Munger Agent - Warren Buffett's partner, only buys wonderful businesses at fair prices
6. Michael Burry Agent - The Big Short contrarian who hunts for deep value
7. Mohnish Pabrai Agent - The Dhandho investor, who looks for doubles at low risk
8. Nassim Taleb Agent - The Black Swan risk analyst, focuses on tail risk, antifragility, and asymmetric payoffs
9. Peter Lynch Agent - Practical investor who seeks "ten-baggers" in everyday businesses
10. Phil Fisher Agent - Meticulous growth investor who uses deep "scuttlebutt" research 
11. Rakesh Jhunjhunwala Agent - The Big Bull of India
12. Stanley Druckenmiller Agent - Macro legend who hunts for asymmetric opportunities with growth potential
13. Warren Buffett Agent - The oracle of Omaha, seeks wonderful companies at a fair price
14. Valuation Agent - Calculates the intrinsic value of a stock and generates trading signals
15. Sentiment Agent - Analyzes market sentiment and generates trading signals
16. Fundamentals Agent - Analyzes fundamental data and generates trading signals
17. Technicals Agent - Analyzes technical indicators and generates trading signals
18. Risk Manager - Calculates risk metrics and sets position limits
19. Portfolio Manager - Makes final trading decisions and generates orders

<img width="1042" alt="Screenshot 2025-03-22 at 6 19 07 PM" src="https://github.com/user-attachments/assets/cbae3dcf-b571-490d-b0ad-3f0f035ac0d4" />

Note: the system does not actually make any trades.

[![Twitter Follow](https://img.shields.io/twitter/follow/virattt?style=social)](https://twitter.com/virattt)

## Disclaimer

This project is for **educational and research purposes only**.

- Not intended for real trading or investment
- No investment advice or guarantees provided
- Creator assumes no liability for financial losses
- Consult a financial advisor for investment decisions
- Past performance does not indicate future results

By using this software, you agree to use it solely for learning purposes.

## Table of Contents
- [How to Install](#how-to-install)
- [How to Run](#how-to-run)
  - [⌨️ Command Line Interface](#️-command-line-interface)
  - [🖥️ Web Application](#️-web-application)
- [How to Contribute](#how-to-contribute)
- [Feature Requests](#feature-requests)
- [License](#license)

## How to Install

Before you can run the AI Hedge Fund, you'll need to install it and set up your API keys. These steps are common to both the full-stack web application and command line interface.

### 1. Clone the Repository

```bash
git clone https://github.com/virattt/ai-hedge-fund.git
cd ai-hedge-fund
```

### 2. Set up API keys

Create a `.env` file for your API keys:
```bash
# Create .env file for your API keys (in the root directory)
cp .env.example .env
```

Open and edit the `.env` file to add your API keys:
```bash
# For running LLMs hosted by openai (gpt-4o, gpt-4o-mini, etc.)
OPENAI_API_KEY=your-openai-api-key

# For getting financial data to power the hedge fund
FINANCIAL_DATASETS_API_KEY=your-financial-datasets-api-key
```

**Important**: You must set at least one LLM API key (e.g. `OPENAI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, or `DEEPSEEK_API_KEY`) for the hedge fund to work. 

## How to Run

### ⌨️ Command Line Interface

You can run the AI Hedge Fund directly via terminal. This approach offers more granular control and is useful for automation, scripting, and integration purposes.

<img width="992" alt="Screenshot 2025-01-06 at 5 50 17 PM" src="https://github.com/user-attachments/assets/e8ca04bf-9989-4a7d-a8b4-34e04666663b" />

#### Quick Start

1. Install Poetry (if not already installed):
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

2. Install dependencies:
```bash
poetry install
```

#### Run the AI Hedge Fund
```bash
poetry run python src/main.py --ticker AAPL,MSFT,NVDA
```

You can also specify a `--ollama` flag to run the AI hedge fund using local LLMs.

```bash
poetry run python src/main.py --ticker AAPL,MSFT,NVDA --ollama
```

You can optionally specify the start and end dates to make decisions over a specific time period.

```bash
poetry run python src/main.py --ticker AAPL,MSFT,NVDA --start-date 2024-01-01 --end-date 2024-03-01
```

#### Run the Backtester
```bash
poetry run python src/backtester.py --ticker AAPL,MSFT,NVDA
```

**Example Output:**
<img width="941" alt="Screenshot 2025-01-06 at 5 47 52 PM" src="https://github.com/user-attachments/assets/00e794ea-8628-44e6-9a84-8f8a31ad3b47" />


Note: The `--ollama`, `--start-date`, and `--end-date` flags work for the backtester, as well!

### 🖥️ Web Application

The new way to run the AI Hedge Fund is through our web application that provides a user-friendly interface. This is recommended for users who prefer visual interfaces over command line tools.

Please see detailed instructions on how to install and run the web application [here](https://github.com/virattt/ai-hedge-fund/tree/main/app).

<img width="1721" alt="Screenshot 2025-06-28 at 6 41 03 PM" src="https://github.com/user-attachments/assets/b95ab696-c9f4-416c-9ad1-51feb1f5374b" />


## How to Contribute

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

**Important**: Please keep your pull requests small and focused.  This will make it easier to review and merge.

## Feature Requests

If you have a feature request, please open an [issue](https://github.com/virattt/ai-hedge-fund/issues) and make sure it is tagged with `enhancement`.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
