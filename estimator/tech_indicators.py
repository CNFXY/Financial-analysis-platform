# -*- coding: utf-8 -*-
"""技术指标分析模块 - 基于 stock-tech-analysis Skill

从 OHLCV 数据计算 15+ 技术指标，并生成多空信号汇总。
支持：MA, MACD, RSI, KDJ, Bollinger Bands, ATR, ADX, OBV, VWAP, MFI, CCI, Williams %R, ROC, TRIX
"""
import numpy as np
import pandas as pd


class TechnicalIndicators:
    """技术指标计算引擎"""

    @staticmethod
    def ensure_ohlcv(data):
        """确保数据包含 OHLCV 列
        
        Args:
            data: DataFrame 或 dict，包含 close/high/low/open/volume
        
        Returns:
            dict: {open, high, low, close, volume}
        """
        if isinstance(data, pd.DataFrame):
            close = data['close'].values if 'close' in data.columns else data['Close'].values
            high = data['high'].values if 'high' in data.columns else data['High'].values
            low = data['low'].values if 'low' in data.columns else data['Low'].values
            open_p = data['open'].values if 'open' in data.columns else data['Open'].values
            volume = data['volume'].values if 'volume' in data.columns else data['Volume'].values
            return {"open": open_p, "high": high, "low": low, "close": close, "volume": volume}
        return data

    # ==================== 均线指标 ====================
    @staticmethod
    def sma(series, window):
        """简单移动平均"""
        if len(series) < window:
            return None
        return np.convolve(series, np.ones(window) / window, mode='valid')

    @staticmethod
    def ema(series, span):
        """指数移动平均"""
        if len(series) < 2:
            return None
        alpha = 2 / (span + 1)
        ema_vals = [series[0]]
        for val in series[1:]:
            ema_vals.append(alpha * val + (1 - alpha) * ema_vals[-1])
        return np.array(ema_vals)

    # ==================== MACD ====================
    @staticmethod
    def macd(close, fast=12, slow=26, signal=9):
        """MACD 指标
        
        Returns:
            dict: {macd_line, signal_line, histogram}
        """
        if len(close) < slow + signal:
            return {}
        ema_fast = TechnicalIndicators.ema(close, fast)
        ema_slow = TechnicalIndicators.ema(close, slow)
        # 对齐长度
        min_len = min(len(ema_fast), len(ema_slow))
        ema_fast = ema_fast[-min_len:]
        ema_slow = ema_slow[-min_len:]
        
        macd_line = ema_fast - ema_slow
        signal_line = TechnicalIndicators.ema(macd_line, signal)
        
        # 对齐 histogram
        hist_len = min(len(macd_line), len(signal_line))
        histogram = macd_line[-hist_len:] - signal_line[-hist_len:]
        
        return {
            "macd_line": macd_line[-hist_len:],
            "signal_line": signal_line,
            "histogram": histogram,
        }

    # ==================== RSI ====================
    @staticmethod
    def rsi(close, window=14):
        """相对强弱指数 RSI"""
        if len(close) < window + 1:
            return None
        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[:window])
        avg_loss = np.mean(losses[:window])
        
        rsi_vals = []
        for i in range(window, len(deltas)):
            avg_gain = (avg_gain * (window - 1) + gains[i]) / window
            avg_loss = (avg_loss * (window - 1) + losses[i]) / window
            if avg_loss == 0:
                rsi_vals.append(100)
            else:
                rs = avg_gain / avg_loss
                rsi_vals.append(100 - (100 / (1 + rs)))
        
        return np.array(rsi_vals)

    # ==================== 布林带 ====================
    @staticmethod
    def bollinger_bands(close, window=20, num_std=2):
        """布林带"""
        if len(close) < window:
            return {}
        sma = np.convolve(close, np.ones(window) / window, mode='valid')
        std = np.array([np.std(close[i:i+window]) for i in range(len(close) - window + 1)])
        upper = sma + num_std * std
        lower = sma - num_std * std
        return {
            "upper": upper,
            "middle": sma,
            "lower": lower,
        }

    # ==================== KDJ ====================
    @staticmethod
    def kdj(high, low, close, n=9, m1=3, m2=3):
        """KDJ 随机指标
        
        Returns:
            dict: {K, D, J}
        """
        if len(close) < n:
            return {}
        
        rsv = []
        for i in range(n - 1, len(close)):
            highest = np.max(high[i - n + 1:i + 1])
            lowest = np.min(low[i - n + 1:i + 1])
            if highest == lowest:
                rsv.append(50)
            else:
                rsv.append((close[i] - lowest) / (highest - lowest) * 100)
        
        rsv = np.array(rsv)
        K = np.zeros_like(rsv)
        D = np.zeros_like(rsv)
        K[0] = rsv[0]
        D[0] = rsv[0]
        
        for i in range(1, len(rsv)):
            K[i] = (2 / m1) * rsv[i] + (1 - 2 / m1) * K[i - 1]
            D[i] = (2 / m2) * K[i] + (1 - 2 / m2) * D[i - 1]
        
        J = 3 * K - 2 * D
        return {"K": K, "D": D, "J": J}

    # ==================== ATR ====================
    @staticmethod
    def atr(high, low, close, window=14):
        """平均真实波幅 ATR"""
        if len(close) < window + 1:
            return None
        tr1 = high[1:] - low[1:]
        tr2 = np.abs(high[1:] - close[:-1])
        tr3 = np.abs(low[1:] - close[:-1])
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        
        atr_vals = [np.mean(tr[:window])]
        for i in range(window, len(tr)):
            atr_vals.append((atr_vals[-1] * (window - 1) + tr[i]) / window)
        
        return np.array(atr_vals)

    # ==================== ADX / DMI ====================
    @staticmethod
    def adx_dmi(high, low, close, window=14):
        """ADX 和 DMI 指标"""
        if len(close) < window + 1:
            return {}
        
        up_move = high[1:] - high[:-1]
        down_move = low[:-1] - low[1:]
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        tr1 = high[1:] - low[1:]
        tr2 = np.abs(high[1:] - close[:-1])
        tr3 = np.abs(low[1:] - close[:-1])
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        
        # Wilder smoothing
        atr_vals = [np.mean(tr[:window])]
        plus_di_vals = [np.mean(plus_dm[:window])]
        minus_di_vals = [np.mean(minus_dm[:window])]
        
        for i in range(window, len(tr)):
            atr_vals.append((atr_vals[-1] * (window - 1) + tr[i]) / window)
            plus_di_vals.append((plus_di_vals[-1] * (window - 1) + plus_dm[i]) / window)
            minus_di_vals.append((minus_di_vals[-1] * (window - 1) + minus_dm[i]) / window)
        
        atr_vals = np.array(atr_vals)
        plus_di = np.array(plus_di_vals) / atr_vals * 100
        minus_di = np.array(minus_di_vals) / atr_vals * 100
        
        dx = np.abs(plus_di - minus_di) / (plus_di + minus_di) * 100
        dx = np.where((plus_di + minus_di) == 0, 0, dx)
        
        adx_vals = [np.mean(dx[:window])]
        for i in range(window, len(dx)):
            adx_vals.append((adx_vals[-1] * (window - 1) + dx[i]) / window)
        
        return {
            "adx": np.array(adx_vals),
            "plus_di": plus_di[-len(adx_vals):],
            "minus_di": minus_di[-len(adx_vals):],
        }

    # ==================== OBV ====================
    @staticmethod
    def obv(close, volume):
        """能量潮 OBV"""
        if len(close) < 2:
            return None
        obv_vals = [volume[0]]
        for i in range(1, len(close)):
            if close[i] > close[i - 1]:
                obv_vals.append(obv_vals[-1] + volume[i])
            elif close[i] < close[i - 1]:
                obv_vals.append(obv_vals[-1] - volume[i])
            else:
                obv_vals.append(obv_vals[-1])
        return np.array(obv_vals)

    # ==================== VWAP ====================
    @staticmethod
    def vwap(high, low, close, volume):
        """成交量加权平均价 VWAP"""
        if len(close) < 1:
            return None
        tp = (high + low + close) / 3
        cum_tp_vol = np.cumsum(tp * volume)
        cum_vol = np.cumsum(volume)
        return cum_tp_vol / cum_vol

    # ==================== MFI ====================
    @staticmethod
    def mfi(high, low, close, volume, window=14):
        """资金流量指数 MFI"""
        if len(close) < window + 1:
            return None
        tp = (high + low + close) / 3
        mf = tp * volume
        
        pmf = np.where(np.diff(tp) > 0, mf[1:], 0)
        nmf = np.where(np.diff(tp) <= 0, mf[1:], 0)
        
        mfi_vals = []
        for i in range(window, len(pmf)):
            pos_sum = np.sum(pmf[i - window + 1:i + 1])
            neg_sum = np.sum(nmf[i - window + 1:i + 1])
            if neg_sum == 0:
                mfi_vals.append(100)
            else:
                mr = pos_sum / neg_sum
                mfi_vals.append(100 - (100 / (1 + mr)))
        
        return np.array(mfi_vals)

    # ==================== CCI ====================
    @staticmethod
    def cci(high, low, close, window=20):
        """顺势指标 CCI"""
        if len(close) < window:
            return None
        tp = (high + low + close) / 3
        cci_vals = []
        for i in range(window - 1, len(tp)):
            sma_tp = np.mean(tp[i - window + 1:i + 1])
            mean_dev = np.mean(np.abs(tp[i - window + 1:i + 1] - sma_tp))
            if mean_dev == 0:
                cci_vals.append(0)
            else:
                cci_vals.append((tp[i] - sma_tp) / (0.015 * mean_dev))
        return np.array(cci_vals)

    # ==================== Williams %R ====================
    @staticmethod
    def williams_r(high, low, close, window=14):
        """威廉指标 %R"""
        if len(close) < window:
            return None
        wr_vals = []
        for i in range(window - 1, len(close)):
            highest = np.max(high[i - window + 1:i + 1])
            lowest = np.min(low[i - window + 1:i + 1])
            if highest == lowest:
                wr_vals.append(-50)
            else:
                wr_vals.append((highest - close[i]) / (highest - lowest) * -100)
        return np.array(wr_vals)

    # ==================== ROC ====================
    @staticmethod
    def roc(close, window=12):
        """变动速率 ROC"""
        if len(close) < window:
            return None
        return (close[window:] - close[:-window]) / close[:-window] * 100

    # ==================== TRIX ====================
    @staticmethod
    def trix(close, window=15):
        """三重指数平滑平均线"""
        if len(close) < window * 3:
            return None
        ema1 = TechnicalIndicators.ema(close, window)
        ema2 = TechnicalIndicators.ema(ema1, window)
        ema3 = TechnicalIndicators.ema(ema2, window)
        
        if len(ema3) < 2:
            return None
        trix_vals = (ema3[1:] - ema3[:-1]) / ema3[:-1] * 100
        return trix_vals

    # ==================== 综合信号判定 ====================
    @staticmethod
    def generate_signals(close, high, low, volume):
        """生成所有指标的信号汇总
        
        Returns:
            dict: 各指标最新信号 + 综合判断
        """
        signals = {}
        
        # 1. MA 交叉
        sma5 = TechnicalIndicators.sma(close, 5)
        sma20 = TechnicalIndicators.sma(close, 20)
        if sma5 is not None and sma20 is not None and len(sma5) > 0 and len(sma20) > 0:
            signals["MA_Cross"] = "bullish" if sma5[-1] > sma20[-1] else "bearish"
        
        # 2. MACD
        macd_result = TechnicalIndicators.macd(close)
        if macd_result and len(macd_result.get("histogram", [])) > 0:
            signals["MACD"] = "bullish" if macd_result["histogram"][-1] > 0 else "bearish"
        
        # 3. RSI
        rsi_vals = TechnicalIndicators.rsi(close, 14)
        if rsi_vals is not None and len(rsi_vals) > 0:
            rsi_last = rsi_vals[-1]
            if rsi_last < 30:
                signals["RSI"] = "bullish"
            elif rsi_last > 70:
                signals["RSI"] = "bearish"
            else:
                signals["RSI"] = "neutral"
        
        # 4. 布林带
        bb = TechnicalIndicators.bollinger_bands(close, 20)
        if bb and len(bb.get("upper", [])) > 0:
            current = close[-1]
            upper = bb["upper"][-1]
            lower = bb["lower"][-1]
            if current < lower:
                signals["Bollinger"] = "bullish"
            elif current > upper:
                signals["Bollinger"] = "bearish"
            else:
                signals["Bollinger"] = "neutral"
        
        # 5. KDJ
        kdj = TechnicalIndicators.kdj(high, low, close, 9, 3, 3)
        if kdj and len(kdj.get("J", [])) > 0:
            j = kdj["J"][-1]
            k = kdj["K"][-1]
            d = kdj["D"][-1]
            if j < 20 or k > d:
                signals["KDJ"] = "bullish"
            elif j > 80 or k < d:
                signals["KDJ"] = "bearish"
            else:
                signals["KDJ"] = "neutral"
        
        # 6. CCI
        cci_vals = TechnicalIndicators.cci(high, low, close, 20)
        if cci_vals is not None and len(cci_vals) > 0:
            cci_last = cci_vals[-1]
            if cci_last < -100:
                signals["CCI"] = "bullish"
            elif cci_last > 100:
                signals["CCI"] = "bearish"
            else:
                signals["CCI"] = "neutral"
        
        # 7. Williams %R
        wr = TechnicalIndicators.williams_r(high, low, close, 14)
        if wr is not None and len(wr) > 0:
            if wr[-1] < -80:
                signals["Williams_R"] = "bullish"
            elif wr[-1] > -20:
                signals["Williams_R"] = "bearish"
            else:
                signals["Williams_R"] = "neutral"
        
        # 8. ADX/DMI
        adx = TechnicalIndicators.adx_dmi(high, low, close, 14)
        if adx and len(adx.get("adx", [])) > 0:
            adx_last = adx["adx"][-1]
            plus_di = adx["plus_di"][-1]
            minus_di = adx["minus_di"][-1]
            if adx_last > 25 and plus_di > minus_di:
                signals["ADX"] = "bullish"
            elif adx_last > 25 and minus_di > plus_di:
                signals["ADX"] = "bearish"
            else:
                signals["ADX"] = "neutral"
        
        # 9. ROC
        roc_vals = TechnicalIndicators.roc(close, 12)
        if roc_vals is not None and len(roc_vals) > 0:
            signals["ROC"] = "bullish" if roc_vals[-1] > 0 else "bearish"
        
        # 10. MFI
        mfi_vals = TechnicalIndicators.mfi(high, low, close, volume, 14)
        if mfi_vals is not None and len(mfi_vals) > 0:
            mfi_last = mfi_vals[-1]
            if mfi_last < 20:
                signals["MFI"] = "bullish"
            elif mfi_last > 80:
                signals["MFI"] = "bearish"
            else:
                signals["MFI"] = "neutral"
        
        # 11. OBV 趋势
        obv_vals = TechnicalIndicators.obv(close, volume)
        if obv_vals is not None and len(obv_vals) >= 5:
            obv_5d = obv_vals[-5:]
            trend = np.polyfit(range(5), obv_5d, 1)[0]
            signals["OBV"] = "bullish" if trend > 0 else "bearish"
        
        # 12. TRIX
        trix_vals = TechnicalIndicators.trix(close, 15)
        if trix_vals is not None and len(trix_vals) > 0:
            signals["TRIX"] = "bullish" if trix_vals[-1] > 0 else "bearish"
        
        # 综合判断
        bullish = sum(1 for v in signals.values() if v == "bullish")
        bearish = sum(1 for v in signals.values() if v == "bearish")
        neutral = sum(1 for v in signals.values() if v == "neutral")
        total = len(signals)
        
        if total == 0:
            verdict = "neutral"
        elif bullish > bearish + 2:
            verdict = "strongly_bullish"
        elif bullish > bearish:
            verdict = "bullish"
        elif bearish > bullish + 2:
            verdict = "strongly_bearish"
        elif bearish > bullish:
            verdict = "bearish"
        else:
            verdict = "neutral"
        
        return {
            "signals": signals,
            "summary": {
                "verdict": verdict,
                "bullish_count": bullish,
                "bearish_count": bearish,
                "neutral_count": neutral,
                "total_indicators": total,
                "bullish_pct": round(bullish / total * 100, 1) if total > 0 else 0,
            }
        }

    # ==================== 全指标计算 ====================
    @staticmethod
    def compute_all(data):
        """计算所有技术指标并返回完整 DataFrame
        
        Args:
            data: DataFrame with columns [date, open, high, low, close, volume]
        
        Returns:
            dict: {dataframe, signals, metadata}
        """
        ohlcv = TechnicalIndicators.ensure_ohlcv(data)
        close = ohlcv["close"]
        high = ohlcv["high"]
        low = ohlcv["low"]
        open_p = ohlcv["open"]
        volume = ohlcv["volume"]
        
        n = len(close)
        
        # 基础数据
        result_df = pd.DataFrame({
            "close": close,
        })
        
        # 均线
        sma5 = TechnicalIndicators.sma(close, 5)
        sma10 = TechnicalIndicators.sma(close, 10)
        sma20 = TechnicalIndicators.sma(close, 20)
        sma60 = TechnicalIndicators.sma(close, 60)
        ema12 = TechnicalIndicators.ema(close, 12)
        ema26 = TechnicalIndicators.ema(close, 26)
        
        # 对齐到 result_df
        def align(arr, name):
            if arr is None or len(arr) == 0:
                return [None] * n
            pad = n - len(arr)
            return [None] * pad + arr.tolist()
        
        result_df["SMA_5"] = align(sma5, "SMA_5")
        result_df["SMA_10"] = align(sma10, "SMA_10")
        result_df["SMA_20"] = align(sma20, "SMA_20")
        result_df["SMA_60"] = align(sma60, "SMA_60")
        result_df["EMA_12"] = align(ema12, "EMA_12")
        result_df["EMA_26"] = align(ema26, "EMA_26")
        
        # MACD
        macd_r = TechnicalIndicators.macd(close)
        if macd_r:
            macd_len = len(macd_r["histogram"])
            result_df["MACD"] = [None] * (n - macd_len) + macd_r["macd_line"].tolist()
            result_df["MACD_Signal"] = [None] * (n - macd_len) + macd_r["signal_line"].tolist()
            result_df["MACD_Histogram"] = [None] * (n - macd_len) + macd_r["histogram"].tolist()
        
        # RSI
        rsi = TechnicalIndicators.rsi(close, 14)
        if rsi is not None:
            result_df["RSI_14"] = [None] * (n - len(rsi)) + rsi.tolist()
        
        # 布林带
        bb = TechnicalIndicators.bollinger_bands(close, 20)
        if bb:
            bb_len = len(bb["upper"])
            result_df["BB_Upper"] = [None] * (n - bb_len) + bb["upper"].tolist()
            result_df["BB_Middle"] = [None] * (n - bb_len) + bb["middle"].tolist()
            result_df["BB_Lower"] = [None] * (n - bb_len) + bb["lower"].tolist()
        
        # KDJ
        kdj = TechnicalIndicators.kdj(high, low, close, 9, 3, 3)
        if kdj:
            kdj_len = len(kdj["K"])
            result_df["KDJ_K"] = [None] * (n - kdj_len) + kdj["K"].tolist()
            result_df["KDJ_D"] = [None] * (n - kdj_len) + kdj["D"].tolist()
            result_df["KDJ_J"] = [None] * (n - kdj_len) + kdj["J"].tolist()
        
        # ATR
        atr = TechnicalIndicators.atr(high, low, close, 14)
        if atr is not None:
            result_df["ATR_14"] = [None] * (n - len(atr)) + atr.tolist()
        
        # ADX/DMI
        adx = TechnicalIndicators.adx_dmi(high, low, close, 14)
        if adx:
            adx_len = len(adx["adx"])
            result_df["ADX"] = [None] * (n - adx_len) + adx["adx"].tolist()
            result_df["+DI"] = [None] * (n - adx_len) + adx["plus_di"].tolist()
            result_df["-DI"] = [None] * (n - adx_len) + adx["minus_di"].tolist()
        
        # OBV
        obv = TechnicalIndicators.obv(close, volume)
        if obv is not None:
            result_df["OBV"] = obv.tolist()
        
        # VWAP
        vwap = TechnicalIndicators.vwap(high, low, close, volume)
        if vwap is not None:
            result_df["VWAP"] = vwap.tolist()
        
        # MFI
        mfi = TechnicalIndicators.mfi(high, low, close, volume, 14)
        if mfi is not None:
            result_df["MFI_14"] = [None] * (n - len(mfi)) + mfi.tolist()
        
        # CCI
        cci = TechnicalIndicators.cci(high, low, close, 20)
        if cci is not None:
            result_df["CCI_20"] = [None] * (n - len(cci)) + cci.tolist()
        
        # Williams %R
        wr = TechnicalIndicators.williams_r(high, low, close, 14)
        if wr is not None:
            result_df["Williams_R"] = [None] * (n - len(wr)) + wr.tolist()
        
        # ROC
        roc = TechnicalIndicators.roc(close, 12)
        if roc is not None:
            result_df["ROC_12"] = [None] * (n - len(roc)) + roc.tolist()
        
        # TRIX
        trix = TechnicalIndicators.trix(close, 15)
        if trix is not None:
            result_df["TRIX"] = [None] * (n - len(trix)) + trix.tolist()
        
        # 信号
        signals = TechnicalIndicators.generate_signals(close, high, low, volume)
        
        return {
            "dataframe": result_df,
            "signals": signals,
            "metadata": {
                "total_rows": n,
                "indicators_computed": len([c for c in result_df.columns if c != "close"]),
            }
        }


if __name__ == "__main__":
    # 测试用例
    np.random.seed(42)
    n = 120
    base = 100
    returns = np.random.normal(0.0005, 0.015, n)
    close = base * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(np.random.normal(0, 0.01, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.01, n)))
    open_p = close * (1 + np.random.normal(0, 0.005, n))
    volume = np.random.randint(1e6, 1e8, n)
    
    df = pd.DataFrame({
        "close": close,
        "high": high,
        "low": low,
        "open": open_p,
        "volume": volume,
    })
    
    result = TechnicalIndicators.compute_all(df)
    print(f"计算了 {result['metadata']['indicators_computed']} 个指标，共 {result['metadata']['total_rows']} 行")
    print(f"\n信号汇总:")
    print(f"  综合判断: {result['signals']['summary']['verdict']}")
    print(f"  做多信号: {result['signals']['summary']['bullish_count']}")
    print(f"  做空信号: {result['signals']['summary']['bearish_count']}")
    print(f"  中性信号: {result['signals']['summary']['neutral_count']}")
    print(f"\n最新指标值:")
    latest = result['dataframe'].iloc[-1]
    for col in ['SMA_5', 'SMA_20', 'RSI_14', 'MACD_Histogram', 'KDJ_J', 'BB_Upper', 'BB_Lower', 'ATR_14']:
        if col in latest.index:
            print(f"  {col}: {latest[col]}")
