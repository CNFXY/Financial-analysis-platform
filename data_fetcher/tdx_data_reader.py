# -*- coding: utf-8 -*-
"""通达信（TDX）本地数据读取模块

功能:
- 读取通达信 .day 日线数据文件
- 读取通达信 .lc1/.lc5 分钟线数据文件
- 支持上海/深圳/北京市场
- 自动检测通达信安装目录

通达信 .day 文件格式:
- 每条记录 32 字节
- struct: date(uint32) + open(uint32) + high(uint32) + low(uint32) + close(uint32) + volume(uint32) + amount(uint32) + reserved(uint32)
- 价格需要除以 100

通达信 .lc1 文件格式（1分钟线）:
- 每条记录 32 字节
- struct: date_time(uint32) + open(uint32) + high(uint32) + low(uint32) + close(uint32) + volume(uint32) + amount(uint32) + reserved(uint32)
- date_time = 日期*10000 + 时间 (如 202401021030 = 2024-01-02 10:30)
"""
import os
import struct
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class TdxDataReader:
    """通达信本地数据读取器"""

    # 通达信市场代码映射
    MARKET_MAP = {
        "sh": {"name": "上海", "path": "sh/lday"},
        "sz": {"name": "深圳", "path": "sz/lday"},
        "bj": {"name": "北京", "path": "bj/lday"},
    }

    # 常见通达信安装路径
    DEFAULT_PATHS = [
        r"D:\通达信\vipdoc",
        r"D:\new_tdx\vipdoc",
        r"C:\new_tdx\vipdoc",
        r"C:\通达信\vipdoc",
    ]

    def __init__(self, vipdoc_path=None):
        """
        Args:
            vipdoc_path: 通达信 vipdoc 目录路径，None则自动检测
        """
        self.vipdoc_path = vipdoc_path or self._auto_detect_vipdoc()
        self.available = self.vipdoc_path is not None and os.path.exists(self.vipdoc_path)

    def _auto_detect_vipdoc(self):
        """自动检测通达信 vipdoc 目录"""
        for path in self.DEFAULT_PATHS:
            if os.path.exists(path):
                return path
        # 尝试搜索
        for drive in ["C:", "D:", "E:", "F:"]:
            for root_name in ["通达信", "new_tdx", "tdx", "Tdx"]:
                path = os.path.join(drive, root_name, "vipdoc")
                if os.path.exists(path):
                    return path
        return None

    def _read_day_file(self, filepath):
        """读取单个 .day 文件
        
        Returns:
            DataFrame: columns=[date, open, high, low, close, volume, amount]
        """
        if not os.path.exists(filepath):
            return None
        
        with open(filepath, 'rb') as f:
            data = f.read()
        
        record_count = len(data) // 32
        if record_count == 0:
            return None
        
        records = []
        for i in range(record_count):
            offset = i * 32
            record = data[offset:offset + 32]
            date, open_p, high, low, close, volume, amount, _ = struct.unpack('IIIIIIII', record)
            records.append({
                'date': str(date),
                'open': open_p / 100.0,
                'high': high / 100.0,
                'low': low / 100.0,
                'close': close / 100.0,
                'volume': volume,
                'amount': amount,
            })
        
        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        df = df.sort_values('date').reset_index(drop=True)
        return df

    def _read_min1_file(self, filepath):
        """读取单个 .lc1 文件（1分钟线）
        
        Returns:
            DataFrame: columns=[datetime, open, high, low, close, volume, amount]
        """
        if not os.path.exists(filepath):
            return None
        
        with open(filepath, 'rb') as f:
            data = f.read()
        
        record_count = len(data) // 32
        if record_count == 0:
            return None
        
        records = []
        for i in range(record_count):
            offset = i * 32
            record = data[offset:offset + 32]
            date_time, open_p, high, low, close, volume, amount, _ = struct.unpack('IIIIIIII', record)
            # date_time = 日期*10000 + 时间 (HHMM)
            date_str = str(date_time // 10000)
            time_str = str(date_time % 10000).zfill(4)
            dt_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}"
            records.append({
                'datetime': dt_str,
                'open': open_p / 100.0,
                'high': high / 100.0,
                'low': low / 100.0,
                'close': close / 100.0,
                'volume': volume,
                'amount': amount,
            })
        
        df = pd.DataFrame(records)
        df['datetime'] = pd.to_datetime(df['datetime'])
        df['date'] = df['datetime'].dt.date
        df = df.sort_values('datetime').reset_index(drop=True)
        return df

    def _get_market_prefix(self, code):
        """根据代码判断市场前缀
        
        Args:
            code: 股票/基金代码，如 "510300" 或 "sh510300"
        
        Returns:
            str: market_prefix + filename, 如 "sh/lday/sh510300.day"
        """
        code = code.upper().replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
        
        # 如果已带前缀
        if code.startswith('SH'):
            return f"sh/lday/{code.lower()}.day"
        elif code.startswith('SZ'):
            return f"sz/lday/{code.lower()}.day"
        elif code.startswith('BJ'):
            return f"bj/lday/{code.lower()}.day"
        
        # 根据代码规则判断
        # 上海: 60xxxx, 51xxxx, 68xxxx, 88xxxx, 99xxxx
        # 深圳: 00xxxx, 30xxxx, 39xxxx, 15xxxx
        # 北京: 43xxxx, 83xxxx, 87xxxx
        if code.startswith(('60', '51', '68', '88', '99')):
            return f"sh/lday/sh{code}.day"
        elif code.startswith(('00', '30', '39', '15')):
            return f"sz/lday/sz{code}.day"
        elif code.startswith(('43', '83', '87')):
            return f"bj/lday/bj{code}.day"
        else:
            # 默认尝试上海和深圳
            return f"sh/lday/sh{code}.day"

    def get_stock_daily(self, code, start_date=None, end_date=None):
        """获取股票/基金日线数据
        
        Args:
            code: 代码，如 "510300" 或 "sh510300"
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        
        Returns:
            DataFrame: columns=[date, open, high, low, close, volume, amount]
        """
        if not self.available:
            return None
        
        relative_path = self._get_market_prefix(code)
        filepath = os.path.join(self.vipdoc_path, relative_path)
        
        # 如果上海没找到，尝试深圳
        if not os.path.exists(filepath):
            alt_path = filepath.replace('sh/lday/', 'sz/lday/').replace('sh', 'sz')
            if os.path.exists(alt_path):
                filepath = alt_path
            else:
                # 尝试北京
                alt_path2 = filepath.replace('sh/lday/', 'bj/lday/').replace('sh', 'bj')
                if os.path.exists(alt_path2):
                    filepath = alt_path2
        
        df = self._read_day_file(filepath)
        if df is None or df.empty:
            return None
        
        # 日期过滤
        if start_date:
            df = df[df['date'] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df['date'] <= pd.to_datetime(end_date)]
        
        return df.reset_index(drop=True)

    def get_stock_minute(self, code, period=1):
        """获取股票/基金分钟线数据
        
        Args:
            code: 代码，如 "510300"
            period: 1 或 5 分钟
        
        Returns:
            DataFrame
        """
        if not self.available:
            return None
        
        relative_path = self._get_market_prefix(code)
        # 分钟线路径
        if period == 1:
            min_path = relative_path.replace('/lday/', '/minline/').replace('.day', '.lc1')
        else:
            min_path = relative_path.replace('/lday/', '/fminline/').replace('.day', '.lc5')
        
        filepath = os.path.join(self.vipdoc_path, min_path)
        
        # 如果上海没找到，尝试深圳
        if not os.path.exists(filepath):
            alt_path = filepath.replace('sh/minline/', 'sz/minline/').replace('sh', 'sz')
            if os.path.exists(alt_path):
                filepath = alt_path
        
        if period == 1:
            return self._read_min1_file(filepath)
        else:
            # 5分钟线格式类似
            return self._read_min1_file(filepath)  # 结构相同

    def get_index_list(self, market='sz'):
        """获取市场下的指数列表
        
        Args:
            market: 'sh', 'sz', 'bj'
        
        Returns:
            list: 指数代码列表
        """
        if not self.available:
            return []
        
        lday_path = os.path.join(self.vipdoc_path, f"{market}/lday")
        if not os.path.exists(lday_path):
            return []
        
        files = [f for f in os.listdir(lday_path) if f.endswith('.day')]
        # 指数通常是 399xxx 或 000xxx
        indices = [f for f in files if f.startswith(f'{market}399') or f.startswith(f'{market}000')]
        return sorted(indices)

    def get_stock_list(self, market='sz'):
        """获取市场下的所有股票/基金列表
        
        Args:
            market: 'sh', 'sz', 'bj'
        
        Returns:
            list: 代码列表
        """
        if not self.available:
            return []
        
        lday_path = os.path.join(self.vipdoc_path, f"{market}/lday")
        if not os.path.exists(lday_path):
            return []
        
        files = [f for f in os.listdir(lday_path) if f.endswith('.day')]
        return sorted(files)

    def get_data_info(self, code):
        """获取数据文件信息
        
        Returns:
            dict: 文件信息
        """
        if not self.available:
            return {"error": "通达信数据目录未找到"}
        
        relative_path = self._get_market_prefix(code)
        filepath = os.path.join(self.vipdoc_path, relative_path)
        
        if not os.path.exists(filepath):
            return {"error": f"文件不存在: {filepath}"}
        
        df = self._read_day_file(filepath)
        if df is None:
            return {"error": "无法读取数据"}
        
        return {
            "code": code,
            "file_path": filepath,
            "file_size_mb": round(os.path.getsize(filepath) / 1024 / 1024, 2),
            "total_records": len(df),
            "date_range": f"{df['date'].min().strftime('%Y-%m-%d')} ~ {df['date'].max().strftime('%Y-%m-%d')}",
            "last_close": round(df['close'].iloc[-1], 2),
            "first_close": round(df['close'].iloc[0], 2),
        }

    def get_status(self):
        """获取通达信数据状态"""
        if not self.available:
            return {
                "available": False,
                "message": "通达信数据目录未找到，请检查安装路径",
                "searched_paths": self.DEFAULT_PATHS,
            }
        
        markets = {}
        for m in ['sh', 'sz', 'bj']:
            lday_path = os.path.join(self.vipdoc_path, f"{m}/lday")
            if os.path.exists(lday_path):
                count = len([f for f in os.listdir(lday_path) if f.endswith('.day')])
                markets[m] = {"files": count}
        
        return {
            "available": True,
            "vipdoc_path": self.vipdoc_path,
            "markets": markets,
        }


if __name__ == "__main__":
    reader = TdxDataReader()
    
    print("=== 通达信数据状态 ===")
    status = reader.get_status()
    print(status)
    
    if status["available"]:
        print("\n=== 读取深证成指 (399001) ===")
        df = reader.get_stock_daily("399001")
        if df is not None:
            print(f"记录数: {len(df)}")
            print(f"日期范围: {df['date'].min()} ~ {df['date'].max()}")
            print(f"最新5条:")
            print(df.tail())
        
        print("\n=== 数据信息 ===")
        info = reader.get_data_info("399001")
        print(info)
    else:
        print("\n通达信数据不可用，请检查安装路径")
        print("常见路径:")
        for p in reader.DEFAULT_PATHS:
            print(f"  {p}")
