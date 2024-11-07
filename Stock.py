import re
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import tushare as ts

class Stock:
    """One tool for stock analysis."""

    def __init__(self, stock_code_path: str, stock_basic_path: str = 'stock_basic.csv') -> None:
        """Initialization."""
        selected_stock = pd.read_excel(stock_code_path)
        stock_basic = pd.read_csv(stock_basic_path, index_col=None)
        selected_stock.rename(columns={'代码': 'ts_code'}, inplace=True)
        tmp = selected_stock.merge(stock_basic[['ts_code', 'name']], on='ts_code', how='left')

        if (tmp['name'] != tmp['名称']).any():
            tmp[tmp['name'] != tmp['名称']].to_excel('./check_code.xlsx', index=False)
            raise ValueError('请检查代码与名称是否有误！\ncheck_code.xlsx中有可能错误的代码或者名称')
        
        self.selected_stock = selected_stock
        self.stock_basic = stock_basic
        self.ts_code_ls = selected_stock['ts_code'].tolist()
        self.ts_code_str = ','.join(self.ts_code_ls)
        self.concepts = selected_stock['概念'].unique().tolist()
        self.stock_num = self.selected_stock.shape[0]
        if self.stock_num != self.ts_code_str.count(',') + 1:
            print(f"shape0_num{self.stock_num}")
            print(f"str_num{self.ts_code_str.count(',') + 1}")
            raise ValueError("stock_num is wrong!")

    def get_today_date(self):
        """Return today's datetime in YYYYMMDD format."""
        return datetime.now().strftime("%Y%m%d")

    def get_limit_range(self, stock_code: str) -> float:
        """Returns the daily price limit range based on the stock code."""
        if 'ST' in stock_code.upper():
            return 0.05  
        elif stock_code.startswith(('600', '601', '603', '000', '002')):
            return 0.1  
        elif stock_code.startswith('688'):
            return 0.2  
        elif stock_code.startswith(('300', '003')):
            return 0.2  
        elif stock_code.startswith('8'):
            return 0.3
        else:
            raise ValueError(f"Unknown limit for code {stock_code}")

    
    def calculate(self, current_date: str = 'today', obs_days: int = 5):
        """Calculate kinds of index for analysis."""
        if current_date == 'today':
            current_date = self.get_today_date()
        def start_date(end_date, days):
            end_date_obj = datetime.strptime(end_date, '%Y%m%d')
            start_date_obj = end_date_obj - timedelta(days=days)
            return start_date_obj.strftime('%Y%m%d')

        pro = ts.pro_api(token='246c3b1bbccd488de181307eaa837a1e1b8c6d369926f9beef611f2f')
        try:
            df = pro.daily(ts_code=self.ts_code_str, start_date=start_date(current_date, obs_days), end_date=current_date)
        except Exception as e:
            print(f"获取数据失败:{e}")
            return None
        while df.shape[0] < self.stock_num * (obs_days + 1):
            try:
                df = pro.daily(ts_code=self.ts_code_str, start_date=start_date(current_date, obs_days + (df.shape[0] / self.stock_num)), end_date=current_date)
            except Exception as e:
                print(f"获取数据失败:{e}")
                return None

        df = df.sort_values('trade_date', ascending=True)
        df['limit_rannge'] = df['ts_code'].apply(lambda code: self.get_limit_range(code))
        df['increase_stop'] = round(df['pre_close'] * (1 + df['limit_rannge']), 2)
        df['amount_change'] = df.groupby('ts_code')['amount'].diff()
        # 放缩
        df.loc[df['amount_change'] > 0, '放缩'] = '放'
        df.loc[df['amount_change'] < 0, '放缩'] = '缩'
        # 涨跌
        df.loc[df['change'] > 0, '涨跌'] = '涨'
        df.loc[df['change'] < 0, '涨跌'] = '跌'
        # 当日是否涨停
        df.loc[df['close'] == df['increase_stop'], '当日是否涨停'] = '是'
        df.loc[df['close'] != df['increase_stop'], '当日是否涨停'] = '否'
        # 昨日是否涨停
        df['昨日是否涨停'] = df.groupby('ts_code')['当日是否涨停'].shift(1)

        df = self.selected_stock[['概念', '名称', 'ts_code']].merge(df, on='ts_code', how='inner')
        return df
        
    def strategy(self, current_date: str = 'today', obs_days: int = 5, threshold: int = 3) -> pd.DataFrame:
        """Analyze stocks based on a custom strategy."""
        if threshold > obs_days:
            raise ValueError("threshold should less than obs_days!")
        if current_date == 'today':
            current_date = self.get_today_date()

        df = self.calculate(current_date=current_date, obs_days=obs_days)
        df['flag'] = np.where(((df['放缩'] == '放') & (df['涨跌'] == '涨')) | 
                              ((df['放缩'] == '缩') & (df['涨跌'] == '跌')) | 
                              ((df['放缩'] == '缩') & (df['涨跌'] == '涨') & (df['当日是否涨停'] == '是')), 1, 0)

        date_range = df['trade_date'].unique().tolist()
        date_range.sort(reverse=False)
        df = df[df['trade_date'].isin(date_range[-threshold:])]

        tmp = df.groupby('ts_code').apply(lambda df: pd.Series({
            'index1': df['flag'].sum(axis=0),
            'index2': df[df['昨日是否涨停'] == '否']['amount_change'].abs().max(axis=0)
        }))
        df = df.merge(tmp, on='ts_code', how='left')

        return df

    def report(self, my_strategy, file_name: str = 'nope', **kwargs):
        """Generate a report based on the given strategy."""
        df = my_strategy(**kwargs)
        concepts = self.concepts
        if file_name == 'nope':
            file_name = datetime.now().strftime("%Y%m%d")

        with pd.ExcelWriter(f'./{file_name}.xlsx') as w:
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