from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import tushare as ts

class Stock:
    """One tool for stock analysis."""
    def __init__(self, stock_code_path, stock_basic_path='stock_basic.csv'):
        """Initialization."""
        selected_stock = pd.read_excel(stock_code_path)
        self.ts_code_ls = selected_stock['代码'].tolist()
        res = ''
        for s in self.ts_code_ls:
            res = res + ',' + s
        self.ts_code_str = res[1:]
        self.stock_basic = pd.read_csv(stock_basic_path, index_col=None)
    
    def calculate(self, current_date, obs_days):
        """Calculate kinds of results for analysis."""
        def start_date(end_date, days):
            end_date_obj = datetime.strptime(end_date, '%Y%m%d')
            start_date_obj = end_date_obj - timedelta(days=days)
            return start_date_obj.strftime('%Y%m%d')
        pro = ts.pro_api(token='246c3b1bbccd488de181307eaa837a1e1b8c6d369926f9beef611f2f')
        df = pro.daily(ts_code=self.ts_code_str, start_date=start_date(current_date, obs_days), end_date=current_date)
        while df.shape[0] < (self.ts_code_str.count(',') + 1) * (obs_days + 1):
            df = pro.daily(ts_code=self.ts_code_str, start_date=start_date(current_date, obs_days + (df.shape[0] / (self.ts_code_str.count(',') + 1))), end_date=current_date)

        df = df.sort_values('trade_date', ascending=True)
        df['increase_stop'] = round(df['pre_close'] * 1.1, 2)
        df['vol_change'] = df['vol'].diff()
        # 放缩
        df.loc[df['vol_change'] > 0, '放缩'] = '放'
        df.loc[df['vol_change'] < 0, '放缩'] = '缩'
        # 涨跌
        df.loc[df['change'] > 0, '涨跌'] = '涨'
        df.loc[df['change'] < 0, '涨跌'] = '跌'
        # 是否涨停
        df.loc[df['close'] == df['increase_stop'], '是否涨停'] = '是'
        df.loc[df['close'] != df['increase_stop'], '是否涨停'] = '否'
        # name
        stock_basic = self.stock_basic
        tmp = stock_basic[['name', 'ts_code']].merge(df, on='ts_code', how='inner')
        return tmp
        
    def strategy(self, current_date, obs_days, threshould=3):
        df = self.calculate(current_date=current_date, obs_days=obs_days)
        # flag
        df['flag'] = 0
        df.loc[(df['放缩'] == '放') & (df['涨跌'] == '涨'), 'flag'] = 1
        df.loc[(df['放缩'] == '缩') & (df['涨跌'] == '跌'), 'flag'] = 1
        df.loc[(df['放缩'] == '缩') & (df['涨跌'] == '涨') & (df['是否涨停'] == '是'), 'flag'] = 1
        


        

