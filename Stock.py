from datetime import datetime, timedelta

import re
import numpy as np
import pandas as pd
import tushare as ts

class Stock:
    """One tool for stock analysis."""
    def __init__(self, stock_code_path, stock_basic_path='stock_basic.csv'):
        """Initialization."""
        selected_stock = pd.read_excel(stock_code_path)
        stock_basic = pd.read_csv(stock_basic_path, index_col=None)
        selected_stock.rename(columns={'代码': 'ts_code'}, inplace=True)
        tmp = selected_stock.merge(stock_basic[['ts_code', 'name']], on='ts_code', how='left')
        if (tmp['name'] != tmp['名称']).any():
            print('Please check the code or the name!')
            tmp[tmp['name'] != tmp['名称']].to_excel('./check_code.xlsx', index=False)
            return None
        ts_code_ls = selected_stock['ts_code'].tolist()
        res = ''
        for s in ts_code_ls:
            res = res + ',' + s
        self.ts_code_str = res[1:]
        self.ts_code_ls = ts_code_ls
        self.selected_stock = selected_stock
        self.stock_basic = stock_basic
        self.concept = selected_stock['概念'].unique().tolist()

    
    def calculate(self, current_date='today', obs_days=5):
        """Calculate kinds of index for analysis."""
        if current_date == 'today':
            current_date = datetime.now().strftime("%Y%m%d")
        def start_date(end_date, days):
            end_date_obj = datetime.strptime(end_date, '%Y%m%d')
            start_date_obj = end_date_obj - timedelta(days=days)
            return start_date_obj.strftime('%Y%m%d')
        pro = ts.pro_api(token='246c3b1bbccd488de181307eaa837a1e1b8c6d369926f9beef611f2f')
        df = pro.daily(ts_code=self.ts_code_str, start_date=start_date(current_date, obs_days), end_date=current_date)
        stock_num = self.ts_code_str.count(',') + 1
        while df.shape[0] < stock_num * (obs_days + 1):
            df = pro.daily(ts_code=self.ts_code_str, start_date=start_date(current_date, obs_days + (df.shape[0] / stock_num)), end_date=current_date)

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

        df = self.selected_stock[['概念', '名称', 'ts_code']].merge(df, on='ts_code', how='inner')
        return df
        
    def strategy(self, current_date='today', obs_days=5, threshold=3):
        if threshold > obs_days:
            raise ValueError("threshold should less than obs_days!")
        if current_date == 'today':
            current_date = datetime.now().strftime("%Y%m%d")
        df = self.calculate(current_date=current_date, obs_days=obs_days)
        # flag
        df['flag'] = 0
        df.loc[(df['放缩'] == '放') & (df['涨跌'] == '涨'), 'flag'] = 1
        df.loc[(df['放缩'] == '缩') & (df['涨跌'] == '跌'), 'flag'] = 1
        df.loc[(df['放缩'] == '缩') & (df['涨跌'] == '涨') & (df['是否涨停'] == '是'), 'flag'] = 1

        date_range = df['trade_date'].unique().tolist()
        date_range.sort(reverse=False)

        df = df[df['trade_date'].isin(date_range[-threshold:])]

        tmp = df.groupby('ts_code').apply(lambda df: pd.Series({
            'index1': df['flag'].sum(axis=0),
            'index2': df['vol_change'].abs().max(axis=0)
        }))
        df = df.merge(tmp, on='ts_code', how='left')

        return df

    def report(self, my_strategy, file_name='nope', **kwargs):
        df = my_strategy(**kwargs)
        concepts = df['概念'].unique().tolist()

        if file_name == 'nope':
            file_name = datetime.now().strftime("%Y%m%d")

        w = pd.ExcelWriter(f'./{file_name}.xlsx')
        for concept in concepts:
            startrow, startcol = 1, 1
            df_concept = df[df['概念'] == concept]
            df_concept = df_concept.sort_values(by=['index1', 'index2'], ascending=[False, False])
            codes = df_concept['ts_code'].unique().tolist()

            safe_concept = re.sub(r'[\/:*?"<>|]', '_', concept)

            for code in codes:
                df_code = df_concept[df_concept['ts_code'] == code]
                df_code.to_excel(w, sheet_name=safe_concept, startrow=startrow, startcol=startcol, index=None)
                startrow += df_code.shape[0] + 3


        w.close()
        