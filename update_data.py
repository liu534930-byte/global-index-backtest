#!/usr/bin/env python3
"""Fetch real monthly market data for the static GitHub Pages dashboard."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
USER_AGENT = "Mozilla/5.0 (compatible; global-index-backtest/1.0)"

GLOBAL = [
    ("gold", "黄金（COMEX连续合约）", "GC=F"),
    ("dow", "道琼斯工业指数", "^DJI"),
    ("nasdaq", "纳斯达克综合指数", "^IXIC"),
    ("sp500", "标普500", "^GSPC"),
    ("ndx", "纳斯达克100", "^NDX"),
]

CHINA = [
    ("sse", "上证指数", ["1.000001", "0.000001"], "sh000001", "000001.SS"),
    ("csi300", "沪深300", ["1.000300", "0.000300", "2.000300"], "sh000300", "000300.SS"),
    ("sse50", "上证50", ["1.000016", "0.000016"], "sh000016", "000016.SS"),
    ("csi500", "中证500", ["1.000905", "2.000905", "0.000905"], "sh000905", "000905.SS"),
    ("chinext", "创业板指", ["0.399006", "1.399006"], "sz399006", "399006.SZ"),
    ("star50", "科创50", ["1.000688", "0.000688"], "sh000688", "000688.SS"),
]


def get_json(url: str, attempts: int = 3) -> dict:
    last_error = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urlopen(request, timeout=35) as response:
                return json.load(response)
        except Exception as exc:  # GitHub runner network errors are usually transient.
            last_error = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Unable to fetch {url}: {last_error}")


def yahoo_monthly(symbol: str) -> list[dict]:
    end = int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp())
    points = {}
    for interval in ("1mo", "1d"):
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{quote(symbol, safe='')}?period1=946684800&period2={end}"
            f"&interval={interval}&events=history"
        )
        payload = get_json(url)
        result = payload.get("chart", {}).get("result") or []
        if not result:
            continue
        chart = result[0]
        closes = chart["indicators"]["quote"][0]["close"]
        points = {}
        for stamp, close in zip(chart.get("timestamp", []), closes):
            if isinstance(close, (int, float)) and close > 0:
                month = datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m")
                points[month] = round(float(close), 8)
        if len(points) >= 12:
            break
    if len(points) < 12:
        raise RuntimeError(f"Yahoo returned insufficient data for {symbol}")
    time.sleep(0.35)
    return [{"date": month, "close": close} for month, close in sorted(points.items())]


def eastmoney_monthly(candidates: list[str]) -> list[dict]:
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "103",
        "fqt": "0",
        "beg": "20000101",
        "end": datetime.now(timezone.utc).strftime("%Y%m%d"),
    }
    for secid in candidates:
        try:
            payload = get_json(
                "https://push2his.eastmoney.com/api/qt/stock/kline/get?"
                + urlencode({"secid": secid, **params}),
                attempts=2,
            )
            rows = (payload.get("data") or {}).get("klines") or []
            points = []
            for row in rows:
                fields = row.split(",")
                close = float(fields[2])
                if close > 0:
                    points.append({"date": fields[0][:7], "close": round(close, 8)})
            if len(points) >= 12:
                return points
        except Exception:
            continue
    raise RuntimeError(f"Eastmoney returned no data for {candidates[0]}")


def tencent_monthly(symbol: str) -> list[dict]:
    url = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
        + urlencode({"param": f"{symbol},month,,,640,qfq"})
    )
    payload = get_json(url)
    block = (payload.get("data") or {}).get(symbol) or {}
    rows = block.get("qfqmonth") or block.get("month") or []
    points = []
    for row in rows:
        if len(row) >= 3:
            close = float(row[2])
            if close > 0:
                points.append({"date": row[0][:7], "close": round(close, 8)})
    if len(points) < 12:
        raise RuntimeError(f"Tencent returned insufficient data for {symbol}")
    return points


def main() -> None:
    fx_points = yahoo_monthly("CNY=X")
    fx_by_month = {point["date"]: point["close"] for point in fx_points}
    series = []

    for asset_id, name, ticker in GLOBAL:
        points = []
        for point in yahoo_monthly(ticker):
            fx = fx_by_month.get(point["date"])
            if fx:
                points.append({**point, "fx": fx})
        if len(points) < 12:
            raise RuntimeError(f"Insufficient FX-aligned data for {ticker}")
        series.append(
            {
                "id": asset_id,
                "name": name,
                "group": "全球",
                "currency": "USD",
                "source": "Yahoo Finance",
                "points": points,
            }
        )

    for asset_id, name, secids, tencent_symbol, yahoo_symbol in CHINA:
        source = "东方财富"
        try:
            points = eastmoney_monthly(secids)
        except Exception:
            try:
                points = tencent_monthly(tencent_symbol)
                source = "腾讯证券（东方财富备用源）"
            except Exception:
                points = yahoo_monthly(yahoo_symbol)
                source = "Yahoo Finance（东方财富、腾讯证券备用源）"
        series.append(
            {
                "id": asset_id,
                "name": name,
                "group": "中国",
                "currency": "CNY",
                "source": source,
                "points": points,
            }
        )

    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "series": series,
        "warnings": [],
    }
    (ROOT / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
