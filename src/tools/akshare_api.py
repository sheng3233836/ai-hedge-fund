"""
A-share (Chinese stock market) data layer using AKShare.

Provides the same interface as src/tools/api.py but fetches data
from AKShare for Chinese A-share stocks (6-digit numeric ticker codes).

Supported markets:
  Shanghai (SH): 600xxx, 601xxx, 603xxx, 605xxx, 688xxx
  Shenzhen (SZ): 000xxx, 001xxx, 002xxx, 003xxx, 300xxx, 301xxx
  Beijing  (BJ): 430xxx, 8xxxxx, 4xxxxx (partial)
"""

import logging
import re
import time
import datetime
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

_RETRY_DELAYS = (2, 5, 10)  # seconds between retries


def _retry_call(fn, *args, retries=3, **kwargs):
    """Call fn(*args, **kwargs) with simple retry on any exception."""
    last_exc: Exception | None = None
    for attempt, delay in enumerate((*_RETRY_DELAYS[:retries - 1], None), 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if delay is not None:
                logger.debug("Attempt %d failed (%s), retrying in %ds…", attempt, e, delay)
                time.sleep(delay)
    raise last_exc

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    logger.warning("akshare not installed. Run: pip install akshare")

from src.data.cache import get_cache
from src.data.models import (
    CompanyNews,
    FinancialMetrics,
    InsiderTrade,
    LineItem,
    Price,
)

_cache = get_cache()

# ---------------------------------------------------------------------------
# Ticker helpers
# ---------------------------------------------------------------------------

def is_astock_ticker(ticker: str) -> bool:
    """Return True if ticker looks like a 6-digit A-share code (e.g. '600519')."""
    return bool(re.match(r"^\d{6}$", ticker.strip()))


def _fmt_date(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' → 'YYYYMMDD' for AKShare APIs."""
    return date_str.replace("-", "")


def _safe_float(val) -> Optional[float]:
    """Convert a value to float, returning None on failure."""
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> Optional[int]:
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _info_dict(symbol: str) -> dict:
    """
    Fetch stock_individual_info_em and return a {item: value} dict.
    Falls back to Baidu valuation API for PE/PB/市值 when EM is unavailable.
    """
    result: dict = {}
    try:
        df = _retry_call(ak.stock_individual_info_em, symbol=symbol)
        result = dict(zip(df["item"], df["value"]))
    except Exception as e:
        # Only log once (final failure), not each retry attempt
        logger.debug("stock_individual_info_em unavailable for %s: %s", symbol, e)

    # Supplement/fallback: Baidu valuation (lighter API, more reliable)
    # Note: Baidu's 总市值 is in 亿元; stock_individual_info_em is in 元 — normalize to 元.
    if not result or result.get("市盈率(TTM)") is None:
        try:
            for bidu_key, out_key, unit_mult in [
                ("市盈率(TTM)", "市盈率(TTM)", 1),
                ("市净率", "市净率", 1),
                ("总市值", "总市值", 1e8),  # Baidu returns 亿 → convert to 元
            ]:
                try:
                    df_b = ak.stock_zh_valuation_baidu(symbol=symbol, indicator=bidu_key)
                    if df_b is not None and not df_b.empty:
                        result[out_key] = df_b["value"].iloc[-1] * unit_mult
                except Exception:
                    pass
        except Exception as e:
            logger.debug("Baidu valuation fallback failed for %s: %s", symbol, e)
    return result


# ---------------------------------------------------------------------------
# Price data
# ---------------------------------------------------------------------------

def _df_to_prices_em(df: pd.DataFrame) -> list[Price]:
    """Parse East-Money style DataFrame (Chinese column names) into Price list."""
    prices: list[Price] = []
    for _, row in df.iterrows():
        try:
            prices.append(
                Price(
                    open=float(row["开盘"]),
                    close=float(row["收盘"]),
                    high=float(row["最高"]),
                    low=float(row["最低"]),
                    volume=int(row["成交量"]),
                    time=str(row["日期"]),
                )
            )
        except Exception:
            continue
    return prices


def _df_to_prices_ths(df: pd.DataFrame) -> list[Price]:
    """Parse THS / 163-style DataFrame into Price list."""
    prices: list[Price] = []
    col_map = {
        "open": ["开盘价", "open", "开盘"],
        "close": ["收盘价", "close", "收盘"],
        "high": ["最高价", "high", "最高"],
        "low": ["最低价", "low", "最低"],
        "volume": ["成交量", "volume", "vol"],
        "date": ["日期", "date", "时间"],
    }

    def _find(cols, candidates):
        for c in candidates:
            if c in cols:
                return c
        return None

    cols = df.columns.tolist()
    c_open = _find(cols, col_map["open"])
    c_close = _find(cols, col_map["close"])
    c_high = _find(cols, col_map["high"])
    c_low = _find(cols, col_map["low"])
    c_vol = _find(cols, col_map["volume"])
    c_date = _find(cols, col_map["date"])

    if not all([c_open, c_close, c_high, c_low, c_vol, c_date]):
        return prices

    for _, row in df.iterrows():
        try:
            prices.append(
                Price(
                    open=float(row[c_open]),
                    close=float(row[c_close]),
                    high=float(row[c_high]),
                    low=float(row[c_low]),
                    volume=int(float(row[c_vol])),
                    time=str(row[c_date])[:10],
                )
            )
        except Exception:
            continue
    return prices


def _ticker_to_exchange_symbol(ticker: str) -> str:
    """Convert bare ticker like '301217' to exchange-prefixed form like 'sz301217'."""
    if ticker.startswith(("sh", "sz", "bj")):
        return ticker
    if ticker.startswith("6"):
        return f"sh{ticker}"
    if ticker.startswith(("4", "8")):
        return f"bj{ticker}"
    return f"sz{ticker}"  # 0xxxxx, 3xxxxx → Shenzhen


def get_prices_astock(ticker: str, start_date: str, end_date: str) -> list[Price]:
    """
    Fetch daily OHLCV for an A-share ticker.

    Primary  : ak.stock_zh_a_hist (East Money, front-adjusted)
    Fallback : ak.stock_zh_kcb_daily (Sina, works for all A-shares incl. ChiNext/STAR)
    Both sources are retried up to 3 times with backoff.
    """
    if not AKSHARE_AVAILABLE:
        return []

    cache_key = f"astock_prices_{ticker}_{start_date}_{end_date}"
    if cached := _cache.get_prices(cache_key):
        return [Price(**p) for p in cached]

    start_fmt = _fmt_date(start_date)
    end_fmt = _fmt_date(end_date)

    # --- Primary: East Money ---
    df = None
    try:
        df = _retry_call(
            ak.stock_zh_a_hist,
            symbol=ticker,
            period="daily",
            start_date=start_fmt,
            end_date=end_fmt,
            adjust="qfq",
        )
    except Exception as e:
        logger.debug("stock_zh_a_hist unavailable for %s: %s", ticker, e)

    if df is not None and not df.empty:
        prices = _df_to_prices_em(df)
        if prices:
            _cache.set_prices(cache_key, [p.model_dump() for p in prices])
            return prices

    # --- Fallback: Sina via stock_zh_kcb_daily (actually works for all A-shares) ---
    logger.debug("Trying fallback price source (Sina kcb_daily) for %s", ticker)
    try:
        exch_symbol = _ticker_to_exchange_symbol(ticker)
        df_fb = _retry_call(ak.stock_zh_kcb_daily, symbol=exch_symbol, adjust="qfq")
        if df_fb is not None and not df_fb.empty:
            # Filter to requested date range (function returns full history)
            mask = (df_fb["date"].astype(str) >= start_date[:10]) & (
                df_fb["date"].astype(str) <= end_date[:10]
            )
            df_fb = df_fb[mask]
            if not df_fb.empty:
                prices = _df_to_prices_ths(df_fb)
                if prices:
                    _cache.set_prices(cache_key, [p.model_dump() for p in prices])
                    return prices
    except Exception as e:
        logger.warning("All price sources failed for %s: %s", ticker, e)
        return []

    logger.warning("All price sources returned empty for %s", ticker)
    df = None

    if df is not None and not df.empty:
        prices = _df_to_prices_ths(df)
        if prices:
            _cache.set_prices(cache_key, [p.model_dump() for p in prices])
            return prices

    logger.warning("All price sources failed for %s", ticker)
    return []


# ---------------------------------------------------------------------------
# Financial Metrics
# ---------------------------------------------------------------------------

def _parse_wan_yi(val) -> Optional[float]:
    """Parse Chinese financial values like '1.23万亿', '456亿', '789万' into raw float."""
    if val is None:
        return None
    s = str(val).replace(",", "").strip()
    if s in ("", "False", "None", "-", "--"):
        return None
    try:
        if "万亿" in s:
            return float(s.replace("万亿", "")) * 1e12
        if "亿" in s:
            return float(s.replace("亿", "")) * 1e8
        if "万" in s:
            return float(s.replace("万", "")) * 1e4
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_pct_str(val) -> Optional[float]:
    """Parse THS/EM percentage strings like '14.65%' or '-30.60%' → ratio 0.1465."""
    if val is None:
        return None
    s = str(val).strip()
    if s in ("", "False", "None", "-", "--"):
        return None
    try:
        if "%" in s:
            return float(s.replace("%", "")) / 100.0
        return float(s) / 100.0
    except (ValueError, TypeError):
        return None


def _from_pct(val) -> Optional[float]:
    """Convert a Sina-style percent float (e.g. 14.65 meaning 14.65%) to ratio (0.1465).
    Sina stores all (%) columns as plain floats like 1.76 for 1.76%."""
    v = _safe_float(val)
    return v / 100.0 if v is not None else None


def get_financial_metrics_astock(
    ticker: str,
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
) -> list[FinancialMetrics]:
    """
    Build FinancialMetrics objects for an A-share ticker.

    Combines:
      1. stock_individual_info_em   → market cap, PE, PB (current snapshot)
      2. stock_financial_abstract_ths → ROE, margins, EPS, BV per share (annual)
    """
    if not AKSHARE_AVAILABLE:
        return []

    cache_key = f"astock_metrics_{ticker}_{period}_{end_date}_{limit}"
    if cached := _cache.get_financial_metrics(cache_key):
        return [FinancialMetrics(**m) for m in cached]

    # --- 1. Current market snapshot ---
    info = _info_dict(ticker)

    market_cap_raw = info.get("总市值") or info.get("市值")
    market_cap = _parse_wan_yi(market_cap_raw)

    pe_ttm = _safe_float(info.get("市盈率(TTM)") or info.get("PE(TTM)") or info.get("PE(动)"))
    pb = _safe_float(info.get("市净率") or info.get("PB") or info.get("市净率(LF)"))

    # --- 2. Historical financial summary (THS source, with fallback to 按报告期) ---
    fin_df: Optional[pd.DataFrame] = None
    for indicator in ("按年度", "按报告期"):
        try:
            fin_df = _retry_call(ak.stock_financial_abstract_ths, symbol=ticker, indicator=indicator)
            if fin_df is not None and not fin_df.empty:
                break
        except Exception as e:
            logger.warning("stock_financial_abstract_ths(%s) failed for %s: %s", indicator, ticker, e)
            fin_df = None

    # --- 3. Detailed ratio data (Sina, try multiple start years since API is range-sensitive) ---
    ratio_df: Optional[pd.DataFrame] = None
    start_year_int = int(end_date[:4]) - 3  # try 3 years back first
    for sy in (start_year_int, start_year_int - 2, start_year_int - 4):
        try:
            ratio_df = _retry_call(
                ak.stock_financial_analysis_indicator, symbol=ticker, start_year=str(sy)
            )
            if ratio_df is not None and not ratio_df.empty:
                break
            ratio_df = None
        except Exception as e:
            logger.debug("stock_financial_analysis_indicator(start_year=%s) failed for %s: %s", sy, ticker, e)
            ratio_df = None

    # -----------------------------------------------------------------------
    # Helper: extract one row of ratios from Sina indicator df (correct columns)
    # -----------------------------------------------------------------------
    def _sina_row(date_str: str) -> Optional[pd.Series]:
        """Return the most recent Sina row at or before date_str."""
        if ratio_df is None or ratio_df.empty:
            return None
        r_date_col = ratio_df.columns[0]
        mask = ratio_df[r_date_col].astype(str).str[:10] <= date_str
        sub = ratio_df[mask]
        # Use iloc[-1] to get the most recent row (data is in ascending order)
        return sub.iloc[-1] if not sub.empty else None

    # -----------------------------------------------------------------------
    # Helper: extract one row from THS abstract df
    # -----------------------------------------------------------------------
    def _ths_row(date_str: str) -> Optional[pd.Series]:
        if fin_df is None or fin_df.empty:
            return None
        date_col = fin_df.columns[0]
        # THS reports are annual (year only like "2023"), try prefix match
        sub = []
        for _, r in fin_df.iterrows():
            d = str(r[date_col]).strip()
            # Normalize: "2023" → "2023-12-31", "2023-03-31" stays
            if len(d) == 4:
                d_full = f"{d}-12-31"
            elif len(d) == 10:
                d_full = d
            else:
                d_full = d[:10]
            if d_full <= date_str:
                sub.append((d_full, r))
        if not sub:
            return None
        sub.sort(key=lambda x: x[0], reverse=True)
        return sub[0][1]

    results: list[FinancialMetrics] = []

    # Determine report dates to iterate over (prefer Sina quarterly, fallback THS annual)
    report_dates: list[str] = []
    if ratio_df is not None and not ratio_df.empty:
        r_date_col = ratio_df.columns[0]
        for d in ratio_df[r_date_col].astype(str).str[:10]:
            if d <= end_date:
                report_dates.append(d)
    elif fin_df is not None and not fin_df.empty:
        date_col = fin_df.columns[0]
        for v in fin_df[date_col]:
            s = str(v).strip()
            d = f"{s}-12-31" if len(s) == 4 else s[:10]
            if d <= end_date:
                report_dates.append(d)

    report_dates = report_dates[:limit]

    for report_date in report_dates:
        sina = _sina_row(report_date)
        ths = _ths_row(report_date)

        # --- Sina (stock_financial_analysis_indicator) column names ---
        # All (%) columns store plain floats where 14.65 means 14.65% → use _from_pct to / 100
        # Non-(%) columns (流动比率 etc.) store ratios directly → use _safe_float
        s = sina if sina is not None else {}
        roe = _from_pct(s.get("净资产收益率(%)"))
        net_margin = _from_pct(s.get("销售净利率(%)"))
        gross_margin = _from_pct(s.get("销售毛利率(%)"))
        op_margin = _from_pct(s.get("营业利润率(%)"))
        roa = _from_pct(s.get("总资产利润率(%)"))
        debt_ratio = _from_pct(s.get("资产负债率(%)"))
        current_ratio = _safe_float(s.get("流动比率"))
        quick_ratio = _safe_float(s.get("速动比率"))
        rev_growth = _from_pct(s.get("主营业务收入增长率(%)"))
        earn_growth = _from_pct(s.get("净利润增长率(%)"))
        eps_sina = _safe_float(s.get("摊薄每股收益(元)"))
        bvps_sina = _safe_float(s.get("每股净资产_调整前(元)"))

        # --- THS fallback for metrics missing/NaN in Sina ---
        # Note: Sina's 销售毛利率(%) is always NaN for some stocks due to EM API bug;
        #       THS abstract provides it reliably as a "14.65%" string.
        if ths is not None:
            if roe is None:
                roe = _parse_pct_str(ths.get("净资产收益率"))
            if net_margin is None:
                net_margin = _parse_pct_str(ths.get("销售净利率"))
            # gross_margin: always supplement from THS since Sina is unreliable for this field
            if gross_margin is None or (sina is not None and pd.isna(sina.get("销售毛利率(%)", float("nan")))):
                gm_ths = _parse_pct_str(ths.get("销售毛利率"))
                if gm_ths is not None:
                    gross_margin = gm_ths
            if current_ratio is None:
                current_ratio = _safe_float(ths.get("流动比率"))
            if quick_ratio is None:
                quick_ratio = _safe_float(ths.get("速动比率"))
            if debt_ratio is None:
                debt_ratio = _parse_pct_str(ths.get("资产负债率"))
            if rev_growth is None:
                rev_growth = _parse_pct_str(ths.get("营业总收入同比增长率"))
            if earn_growth is None:
                earn_growth = _parse_pct_str(ths.get("净利润同比增长率"))

        eps = eps_sina or (_safe_float(ths.get("基本每股收益") if ths is not None else None))
        bvps = bvps_sina or (_safe_float(ths.get("每股净资产") if ths is not None else None))

        results.append(
            FinancialMetrics(
                ticker=ticker,
                report_period=report_date,
                period=period,
                currency="CNY",
                market_cap=market_cap,
                enterprise_value=None,
                price_to_earnings_ratio=pe_ttm,
                price_to_book_ratio=pb,
                price_to_sales_ratio=None,
                enterprise_value_to_ebitda_ratio=None,
                enterprise_value_to_revenue_ratio=None,
                free_cash_flow_yield=None,
                peg_ratio=None,
                gross_margin=gross_margin,
                operating_margin=op_margin,
                net_margin=net_margin,
                return_on_equity=roe,
                return_on_assets=roa,
                return_on_invested_capital=None,
                asset_turnover=None,
                inventory_turnover=None,
                receivables_turnover=None,
                days_sales_outstanding=None,
                operating_cycle=None,
                working_capital_turnover=None,
                current_ratio=current_ratio,
                quick_ratio=quick_ratio,
                cash_ratio=None,
                operating_cash_flow_ratio=None,
                debt_to_equity=debt_ratio,
                debt_to_assets=debt_ratio,
                interest_coverage=None,
                revenue_growth=rev_growth,
                earnings_growth=earn_growth,
                book_value_growth=None,
                earnings_per_share_growth=None,
                free_cash_flow_growth=None,
                operating_income_growth=None,
                ebitda_growth=None,
                payout_ratio=None,
                earnings_per_share=eps,
                book_value_per_share=bvps,
                free_cash_flow_per_share=None,
            )
        )

    # Fallback: build a single metrics entry from current snapshot only
    if not results:
        results.append(
            FinancialMetrics(
                ticker=ticker,
                report_period=end_date,
                period=period,
                currency="CNY",
                market_cap=market_cap,
                enterprise_value=None,
                price_to_earnings_ratio=pe_ttm,
                price_to_book_ratio=pb,
                price_to_sales_ratio=None,
                enterprise_value_to_ebitda_ratio=None,
                enterprise_value_to_revenue_ratio=None,
                free_cash_flow_yield=None,
                peg_ratio=None,
                gross_margin=None,
                operating_margin=None,
                net_margin=None,
                return_on_equity=None,
                return_on_assets=None,
                return_on_invested_capital=None,
                asset_turnover=None,
                inventory_turnover=None,
                receivables_turnover=None,
                days_sales_outstanding=None,
                operating_cycle=None,
                working_capital_turnover=None,
                current_ratio=None,
                quick_ratio=None,
                cash_ratio=None,
                operating_cash_flow_ratio=None,
                debt_to_equity=None,
                debt_to_assets=None,
                interest_coverage=None,
                revenue_growth=None,
                earnings_growth=None,
                book_value_growth=None,
                earnings_per_share_growth=None,
                free_cash_flow_growth=None,
                operating_income_growth=None,
                ebitda_growth=None,
                payout_ratio=None,
                earnings_per_share=None,
                book_value_per_share=None,
                free_cash_flow_per_share=None,
            )
        )

    if results:
        _cache.set_financial_metrics(cache_key, [m.model_dump() for m in results])

    return results


# ---------------------------------------------------------------------------
# Line Items (from financial statements)
# ---------------------------------------------------------------------------

# Maps the generic line-item names used in agents → possible AKShare column names
_BALANCE_SHEET_MAP = {
    "total_assets": ["资产合计", "总资产", "assets_total"],
    "total_liabilities": ["负债合计", "总负债", "liabilities_total"],
    "shareholders_equity": ["归属于母公司所有者权益合计", "所有者权益合计", "equity_total", "股东权益合计"],
    "outstanding_shares": ["实收资本(股本)", "股本", "shares_outstanding"],
    "cash_and_equivalents": ["货币资金", "现金及现金等价物"],
    "total_debt": ["短期借款", "长期借款"],
    "goodwill_and_intangible_assets": ["商誉", "无形资产"],
}

_INCOME_STMT_MAP = {
    "revenue": ["营业收入", "营业总收入", "revenue"],
    "gross_profit": ["毛利润", "gross_profit"],
    "operating_income": ["营业利润", "operating_income"],
    "net_income": ["净利润", "归属于母公司所有者的净利润", "net_income"],
    "ebit": ["息税前利润", "ebit"],
    "ebitda": ["ebitda"],
    "depreciation_and_amortization": ["折旧与摊销", "固定资产折旧、油气资产折耗、生产性生物资产折旧", "depreciation"],
    "interest_expense": ["利息费用", "财务费用", "interest_expense"],
    "income_tax_expense": ["所得税费用", "income_tax"],
    "dividends_and_other_cash_distributions": ["分配股利、利润或偿付利息支付的现金", "支付股利、利润或偿付利息所支付的现金"],
}

_CASH_FLOW_MAP = {
    "operating_cash_flow": ["经营活动产生的现金流量净额", "经营活动现金流量净额", "operating_cash_flow"],
    "capital_expenditure": ["购建固定资产、无形资产和其他长期资产支付的现金", "资本支出", "capital_expenditure"],
    "free_cash_flow": [],  # computed: operating_cf - capex
    "issuance_or_purchase_of_equity_shares": ["发行股票等权益性工具收到的现金", "回购股票等权益性工具支付的现金"],
    "dividends_and_other_cash_distributions": ["分配股利、利润或偿付利息支付的现金", "支付的股利、利润"],
}


def _find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """Return the first matching column name from candidates list."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _extract_val(row, candidates: list[str]) -> Optional[float]:
    for c in candidates:
        if c in row.index:
            return _safe_float(row[c])
    return None


def _get_report_df(fetch_fn, ticker: str, retries: int = 2, **kwargs) -> Optional[pd.DataFrame]:
    """Safely fetch a financial statement DataFrame, with retry."""
    try:
        df = _retry_call(fetch_fn, symbol=ticker, retries=retries, **kwargs)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        logger.warning("Financial statement fetch failed for %s: %s", ticker, e)
    return None


def search_line_items_astock(
    ticker: str,
    line_items: list[str],
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
) -> list[LineItem]:
    """
    Fetch specific financial line items for an A-share ticker.

    Strategy:
      Primary  : EM three-report APIs (balance sheet / income / cash flow)
      Fallback : Derive from Sina indicator + THS abstract when EM fails
                 (EM fails for some stocks due to HTML-parsing company-type detection)
    """
    if not AKSHARE_AVAILABLE:
        return []

    # --- Primary: try EM three-report APIs ---
    def _fetch_with_fallback(em_fn, ticker: str) -> Optional[pd.DataFrame]:
        return _get_report_df(em_fn, ticker)

    bs_df = _fetch_with_fallback(ak.stock_balance_sheet_by_report_em, ticker)
    is_df = _fetch_with_fallback(ak.stock_profit_sheet_by_report_em, ticker)
    cf_df = _fetch_with_fallback(ak.stock_cash_flow_sheet_by_report_em, ticker)

    em_available = any(df is not None for df in [bs_df, is_df, cf_df])

    if em_available:
        # --- Normal path: use EM three-report data ---
        def _filter_rows(df: Optional[pd.DataFrame]) -> list[tuple[str, pd.Series]]:
            if df is None or df.empty:
                return []
            date_col = next(
                (c for c in df.columns if "REPORT_DATE" in c or "报告日期" in c or c == "报告期"),
                df.columns[0],
            )
            rows = []
            for _, row in df.iterrows():
                d = str(row[date_col])[:10]
                if d <= end_date:
                    rows.append((d, row))
            rows.sort(key=lambda x: x[0], reverse=True)
            return rows[:limit]

        bs_rows = _filter_rows(bs_df)
        is_rows = _filter_rows(is_df)
        cf_rows = _filter_rows(cf_df)

        results: list[LineItem] = []
        n = max(len(bs_rows), len(is_rows), len(cf_rows), 1)

        for i in range(min(n, limit)):
            bs_date, bs_row = bs_rows[i] if i < len(bs_rows) else (end_date, pd.Series(dtype=object))
            is_date, is_row = is_rows[i] if i < len(is_rows) else (end_date, pd.Series(dtype=object))
            cf_date, cf_row = cf_rows[i] if i < len(cf_rows) else (end_date, pd.Series(dtype=object))

            report_date = max(filter(None, [bs_date, is_date, cf_date]))
            item_data: dict = {"ticker": ticker, "report_period": report_date, "period": period, "currency": "CNY"}

            for li in line_items:
                val: Optional[float] = None
                if li in _BALANCE_SHEET_MAP:
                    val = _extract_val(bs_row, _BALANCE_SHEET_MAP[li])
                elif li in _INCOME_STMT_MAP:
                    val = _extract_val(is_row, _INCOME_STMT_MAP[li])
                elif li in _CASH_FLOW_MAP:
                    if li == "free_cash_flow":
                        op_cf = _extract_val(cf_row, _CASH_FLOW_MAP["operating_cash_flow"])
                        capex = _extract_val(cf_row, _CASH_FLOW_MAP["capital_expenditure"])
                        if op_cf is not None and capex is not None:
                            val = op_cf - abs(capex)
                    else:
                        val = _extract_val(cf_row, _CASH_FLOW_MAP[li])
                        if li == "capital_expenditure" and val is not None:
                            val = -abs(val)
                if li == "gross_profit" and val is None:
                    rev = _extract_val(is_row, _INCOME_STMT_MAP.get("revenue", []))
                    cogs = _extract_val(is_row, ["营业成本", "主营业务成本", "cost_of_revenue"])
                    if rev is not None and cogs is not None:
                        val = rev - cogs
                item_data[li] = val
            results.append(LineItem(**item_data))
        return results

    # --- Fallback path: derive from Sina indicator + THS abstract ---
    logger.info("EM three-report APIs unavailable for %s, falling back to Sina+THS", ticker)

    sina_df: Optional[pd.DataFrame] = None
    ths_df: Optional[pd.DataFrame] = None
    try:
        sy = str(int(end_date[:4]) - 3)
        for _sy in (sy, str(int(sy) - 2), str(int(sy) - 4)):
            sina_df = _retry_call(ak.stock_financial_analysis_indicator, symbol=ticker, start_year=_sy)
            if sina_df is not None and not sina_df.empty:
                break
            sina_df = None
    except Exception as e:
        logger.warning("Sina indicator failed for %s: %s", ticker, e)

    # THS 按报告期 gives quarterly revenue/net_income; 按年度 as fallback
    for indicator in ("按报告期", "按年度"):
        try:
            ths_df = _retry_call(ak.stock_financial_abstract_ths, symbol=ticker, indicator=indicator)
            if ths_df is not None and not ths_df.empty:
                break
        except Exception:
            ths_df = None

    # Get company-level info (shares, market cap)
    info = _info_dict(ticker)
    total_shares = _safe_float(info.get("总股本")) or _safe_float(info.get("流通股"))

    def _ths_date(v) -> str:
        s = str(v).strip()
        return f"{s}-12-31" if len(s) == 4 else s[:10]

    results_fb: list[LineItem] = []

    # Build date list: prefer Sina quarterly, then THS (which may be quarterly if 按报告期)
    dates: list[str] = []
    if sina_df is not None and not sina_df.empty:
        for d in sina_df[sina_df.columns[0]].astype(str).str[:10]:
            if d <= end_date:
                dates.append(d)
    elif ths_df is not None and not ths_df.empty:
        for v in ths_df[ths_df.columns[0]]:
            d = _ths_date(v)
            if d <= end_date:
                dates.append(d)

    for report_date in dates[:limit]:
        # Find matching Sina row (exact date match)
        s_row: Optional[pd.Series] = None
        if sina_df is not None and not sina_df.empty:
            mask = sina_df[sina_df.columns[0]].astype(str).str[:10] == report_date
            if mask.any():
                s_row = sina_df[mask].iloc[-1]

        # Find matching THS row: exact match first, then most-recent-before
        t_row: Optional[pd.Series] = None
        if ths_df is not None and not ths_df.empty:
            dc = ths_df.columns[0]
            best_d, best_r = "", None
            for _, r in ths_df.iterrows():
                d = _ths_date(r[dc])
                if d <= report_date and d >= best_d:
                    best_d, best_r = d, r
            t_row = best_r

        # Derive values from Sina (s_row) and THS (t_row)
        sr = s_row if s_row is not None else {}
        tr = t_row if t_row is not None else {}
        total_assets = _safe_float(sr.get("总资产(元)"))
        # Sina 资产负债率(%) stores plain percent float (e.g. 14.29 means 14.29%)
        debt_ratio = _from_pct(sr.get("资产负债率(%)")) or _parse_pct_str(tr.get("资产负债率"))
        total_liabilities = (total_assets * debt_ratio) if (total_assets and debt_ratio) else None
        shareholders_equity = (total_assets - total_liabilities) if (total_assets and total_liabilities) else None

        # Revenue and net income from THS (亿-format strings), fallback to Sina per-share × shares
        revenue = _parse_wan_yi(tr.get("营业总收入"))
        net_income = _parse_wan_yi(tr.get("净利润"))

        # Gross margin from THS (string "19.88%"), or from Sina per_pct
        gross_margin_r = _parse_pct_str(tr.get("销售毛利率")) or _from_pct(sr.get("销售毛利率(%)"))
        gross_profit = (revenue * gross_margin_r) if (revenue and gross_margin_r) else None

        # Per-share × total shares → absolute operating cash flow
        eps_cf = _safe_float(tr.get("每股经营现金流"))
        operating_cf = (eps_cf * total_shares) if (eps_cf and total_shares) else None
        free_cash_flow = operating_cf  # approximation when capex unknown

        item_data: dict = {"ticker": ticker, "report_period": report_date, "period": period, "currency": "CNY"}
        _derived = {
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "shareholders_equity": shareholders_equity,
            "outstanding_shares": total_shares,
            "revenue": revenue,
            "net_income": net_income,
            "gross_profit": gross_profit,
            "operating_cash_flow": operating_cf,
            "free_cash_flow": free_cash_flow,
            "capital_expenditure": None,
            "depreciation_and_amortization": None,
            "dividends_and_other_cash_distributions": None,
            "issuance_or_purchase_of_equity_shares": None,
            "operating_income": None,
            "interest_expense": None,
            "ebit": None,
            "ebitda": None,
        }
        for li in line_items:
            item_data[li] = _derived.get(li)
        results_fb.append(LineItem(**item_data))

    return results_fb


# ---------------------------------------------------------------------------
# Insider Trades
# ---------------------------------------------------------------------------

def get_insider_trades_astock(
    ticker: str,
    end_date: str,
    start_date: Optional[str] = None,
    limit: int = 100,
) -> list[InsiderTrade]:
    """
    Fetch insider / major-holder trades for an A-share ticker.

    Uses 大股东增减持 (major shareholder increase/decrease holdings) data.
    Returns an empty list if data is unavailable.
    """
    if not AKSHARE_AVAILABLE:
        return []

    try:
        df = ak.stock_restricted_release_summary_em(symbol=ticker)
    except Exception:
        # Fallback: try major shareholder change data
        try:
            df = ak.stock_em_hold_stocks_change(symbol=ticker)
        except Exception as e:
            logger.debug("Insider trade data unavailable for A-share %s: %s", ticker, e)
            return []

    if df is None or df.empty:
        return []

    trades: list[InsiderTrade] = []
    date_col = df.columns[0]

    for _, row in df.iterrows():
        filing_date = str(row.get(date_col, ""))[:10]
        if start_date and filing_date < start_date:
            continue
        if filing_date > end_date:
            continue

        trades.append(
            InsiderTrade(
                ticker=ticker,
                issuer=ticker,
                name=str(row.get("股东名称", row.get("holder_name", ""))),
                title=str(row.get("股东类型", "major_shareholder")),
                is_board_director=None,
                transaction_date=str(row.get("变动截止日", row.get("date", filing_date)))[:10],
                transaction_shares=_safe_float(row.get("变动数量", row.get("change_shares"))),
                transaction_price_per_share=None,
                transaction_value=_safe_float(row.get("变动金额", row.get("change_amount"))),
                shares_owned_before_transaction=None,
                shares_owned_after_transaction=_safe_float(row.get("变动后持股数", row.get("shares_after"))),
                security_title="A股",
                filing_date=filing_date,
            )
        )
        if len(trades) >= limit:
            break

    return trades


# ---------------------------------------------------------------------------
# Company News
# ---------------------------------------------------------------------------

def get_company_news_astock(
    ticker: str,
    end_date: str,
    start_date: Optional[str] = None,
    limit: int = 50,
) -> list[CompanyNews]:
    """Fetch company-specific news for an A-share ticker via AKShare."""
    if not AKSHARE_AVAILABLE:
        return []

    try:
        df = ak.stock_news_em(symbol=ticker)
    except Exception as e:
        logger.warning("Failed to fetch news for A-share %s: %s", ticker, e)
        return []

    if df is None or df.empty:
        return []

    news_list: list[CompanyNews] = []
    for _, row in df.iterrows():
        pub_time = str(row.get("发布时间", row.get("datetime", "")))
        pub_date = pub_time[:10] if pub_time else ""

        if pub_date and pub_date > end_date:
            continue
        if start_date and pub_date < start_date:
            continue

        title = str(row.get("新闻标题", row.get("title", "")))
        url = str(row.get("新闻链接", row.get("url", "")))
        source = str(row.get("文章来源", row.get("source", "东方财富")))

        news_list.append(
            CompanyNews(
                ticker=ticker,
                title=title,
                author=None,
                source=source,
                date=pub_date,
                url=url,
                sentiment=None,
            )
        )
        if len(news_list) >= limit:
            break

    return news_list


# ---------------------------------------------------------------------------
# Market Cap
# ---------------------------------------------------------------------------

def get_market_cap_astock(ticker: str, end_date: str) -> Optional[float]:
    """
    Return total market cap (CNY) for an A-share ticker.

    Uses stock_individual_info_em for real-time data.
    For historical dates falls back to price × shares outstanding estimate.
    """
    if not AKSHARE_AVAILABLE:
        return None

    info = _info_dict(ticker)
    raw = info.get("总市值") or info.get("市值")
    return _parse_wan_yi(raw)
