# -*- coding: utf-8 -*-
"""全球财经新闻聚合模块 - 真实数据接入

数据来源（按优先级）:
1. MarketWatch Top Stories RSS  (真实、无需 token)
2. CNBC Top News RSS            (真实、无需 token)
3. Yahoo Finance News           (真实，可能被限流)
4. 本地缓存                     (限流/失败时回退)
5. 演示样本                     (最终兜底，保证页面有内容)

所有内容均来自公开 RSS，接入后随真实市场每日更新。
"""
import os
import re
import json
import html
import urllib.request
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

from fund_estimation_system import config

CACHE_DIR = config.CACHE_DIR
CACHE_FILE = os.path.join(CACHE_DIR, "global_news_cache.json")
CACHE_TTL_MINUTES = 30


class NewsFetcher:
    """全球财经新闻获取器"""

    SOURCES = {
        "marketwatch": {
            "url": "https://www.marketwatch.com/rss/topstories",
            "label": "MarketWatch",
            "category": "global",
            "region": "US",
        },
        "cnbc": {
            "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
            "label": "CNBC",
            "category": "global",
            "region": "US",
        },
    }

    @staticmethod
    def _parse_published(raw):
        """将 RSS 时间字符串解析为 ISO 格式"""
        if not raw:
            return datetime.now(timezone.utc).isoformat()
        raw = raw.strip()
        try:
            # RFC 822: 'Mon, 14 Jul 2026 08:00:00 GMT'
            dt = datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S %Z")
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except Exception:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return dt.astimezone(timezone.utc).isoformat()
            except Exception:
                return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _clean_text(text):
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", "", text)  # 去除 HTML 标签
        text = html.unescape(text)
        return text.strip()

    @staticmethod
    def _classify(title, summary):
        """基于关键词对新闻分类"""
        text = (title + " " + summary).lower()
        rules = [
            ("宏观", ["fed", "利率", "通胀", "inflation", "rate", "央行", "gdp", "经济", "economy", "博物", "债券", "bond", "yield"]),
            ("股市", ["stock", "股市", "股指", "指数", "etf", "equity", "nasdaq", "s&p", "a股", "a-share"]),
            ("科技", ["tech", "ai", "芯片", "半导体", "apple", "nvidia", "google", "microsoft", "meta", "tesla", "软件"]),
            ("商品", ["gold", "黄金", "oil", "原油", "commodit", "铜", "crude", "白银", "silver"]),
            ("外汇", ["forex", "美元", "dollar", "eur", "yen", "人民币", "汇率", "currency"]),
            ("加密", ["bitcoin", "crypto", "比特币", "以太坊", "ethereum"]),
            ("公司", ["earnings", "财报", "营收", "profit", "收购", "merger", "ipo"]),
        ]
        for cat, kws in rules:
            if any(k in text for k in kws):
                return cat
        return "综合"

    @staticmethod
    def _region_of(source_label):
        if source_label == "CNBC" or source_label == "MarketWatch":
            return "US"
        return "GLOBAL"

    def _fetch_rss(self, name, meta):
        """获取单个 RSS 源，返回新闻列表"""
        req = urllib.request.Request(
            meta["url"],
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        raw = urllib.request.urlopen(req, timeout=15).read()
        root = ET.fromstring(raw)
        items = root.findall(".//item")
        news = []
        for it in items[:25]:
            title_el = it.find("title")
            link_el = it.find("link")
            desc_el = it.find("description")
            pub_el = it.find("pubDate")
            title = self._clean_text(title_el.text if title_el is not None else "")
            if not title:
                continue
            summary = self._clean_text(desc_el.text if desc_el is not None else "")
            if len(summary) > 220:
                summary = summary[:220] + "…"
            news.append({
                "title": title,
                "summary": summary,
                "source": meta["label"],
                "category": self._classify(title, summary),
                "region": self._region_of(meta["label"]),
                "url": (link_el.text or "#").strip() if link_el is not None else "#",
                "published": self._parse_published(pub_el.text if pub_el is not None else None),
            })
        return news

    def _load_cache(self):
        if not os.path.exists(CACHE_FILE):
            return None
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cached_time = datetime.fromisoformat(data.get("fetched_at", "2000-01-01T00:00:00"))
            if datetime.now() - cached_time < timedelta(minutes=CACHE_TTL_MINUTES):
                return data.get("items", [])
        except Exception:
            pass
        return None

    def _save_cache(self, items):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "fetched_at": datetime.now().isoformat(),
                    "items": items,
                }, f, ensure_ascii=False)
        except Exception:
            pass

    def fetch_news(self, category=None, region=None, limit=40):
        """获取全球财经新闻

        Args:
            category: 过滤类别（宏观/股市/科技/商品/外汇/加密/公司/综合）
            region:   过滤地区（CN/US/GLOBAL）
            limit:    返回条数
        Returns:
            dict: {items, sources, fetched_at, is_demo, count}
        """
        cached = self._load_cache()
        if cached:
            items = cached
            is_demo = False
            sources = sorted({i["source"] for i in items})
        else:
            items = []
            sources = []
            for name, meta in self.SOURCES.items():
                try:
                    got = self._fetch_rss(name, meta)
                    items.extend(got)
                    if got:
                        sources.append(meta["label"])
                except Exception as e:
                    print(f"[WARN] 新闻源 {name} 获取失败: {e}")

            if not items:
                # 尝试 Yahoo 兜底
                items = self._fetch_yahoo_fallback()
                sources = [i["source"] for i in items] or []

            if not items:
                # 无任何真实新闻源可用：如实返回空，绝不编造新闻标题
                print("[WARN] 所有真实新闻源均不可用，返回空列表（不编造演示新闻）")
                is_demo = False
                sources = []
            else:
                is_demo = False
                self._save_cache(items)

        # 排序（新 -> 旧）
        items.sort(key=lambda x: x.get("published", ""), reverse=True)

        # 过滤
        if category and category != "all":
            items = [i for i in items if i.get("category") == category]
        if region and region != "all":
            items = [i for i in items if i.get("region") == region]

        return {
            "items": items[:limit],
            "sources": sorted(set(sources)),
            "fetched_at": datetime.now().isoformat(),
            "is_demo": is_demo,
            "count": len(items[:limit]),
        }

    def _fetch_yahoo_fallback(self):
        """Yahoo 新闻兜底（可能被限流，故置后）"""
        try:
            import yfinance as yf
            t = yf.Ticker("^GSPC")
            news = t.news or []
            out = []
            for n in news[:20]:
                cnt = n.get("content", {})
                title = self._clean_text(cnt.get("title", ""))
                if not title:
                    continue
                out.append({
                    "title": title,
                    "summary": self._clean_text(cnt.get("summary", ""))[:220],
                    "source": "Yahoo Finance",
                    "category": self._classify(title, cnt.get("summary", "")),
                    "region": "US",
                    "url": cnt.get("canonicalUrl", {}).get("url", "#"),
                    "published": self._parse_published(cnt.get("pubDate")),
                })
            return out
        except Exception:
            return []


if __name__ == "__main__":
    f = NewsFetcher()
    r = f.fetch_news()
    print("is_demo:", r["is_demo"], "count:", r["count"], "sources:", r["sources"])
    for n in r["items"][:3]:
        print("-", n["title"])
