from datetime import datetime, timedelta
import re
import numpy as np
import pandas as pd
import tushare as ts

class Stock:
    """A tool for stock analysis."""

    def __init__(self, stock_code_path: str, stock_basic_path: str = 'stock_basic.csv'):
        """Initialization."""
        selected_stock = pd.read_excel(stock_code_path)
        stock_basic = pd.read_csv(stock_basic_path, index_col=None)
        selected_stock.rename(columns={'代码': 'ts_code'}, inplace=True)
        tmp = selected_stock.merge(stock_basic[['ts_code', 'name']], on='ts_code', how='left')
        
        if (tmp['name'] != tmp['名称']).any():
            raise ValueError("请检查代码或名称是否一致！")
        
        self.ts_code_str = ",".join(selected_stock['ts_code'].tolist())
        self.ts_code_ls = selected_stock['ts_code'].tolist()
        self.selected_stock = selected_stock
        self.stock_basic = stock_basic
        self.concept = selected_stock['概念'].unique().tolist()

    def get_current_date(self) -> str:
        """Return the current date in YYYYMMDD format."""
        return datetime.now().strftime("%Y%m%d")

    def calculate(self, current_date: str = 'today', obs_days: int = 5) -> pd.DataFrame:
        """Calculate kinds of index for analysis."""
        if current_date == 'today':
            current_date = self.get_current_date()
        
        def start_date(end_date: str, days: int) -> str:
            end_date_obj = datetime.strptime(end_date, '%Y%m%d')
            start_date_obj = end_date_obj - timedelta(days=days)
            return start_date_obj.strftime('%Y%m%d')
        
        pro = ts.pro_api(token='your_token')
        df = pro.daily(ts_code=self.ts_code_str, start_date=start_date(current_date, obs_days), end_date=current_date)

        df = df.sort_values('trade_date', ascending=True)
        df['increase_stop'] = round(df['pre_close'] * 1.1, 2)
        df['vol_change'] = df['vol'].diff()

        df['放缩'] = np.where(df['vol_change'] > 0, '放', '缩')
        df['涨跌'] = np.where(df['change'] > 0, '涨', '跌')
        df['是否涨停'] = np.where(df['close'] == df['increase_stop'], '是', '否')

        return self.selected_stock[['概念', '名称', 'ts_code']].merge(df, on='ts_code', how='inner')

    def strategy(self, current_date: str = 'today', obs_days: int = 5, threshold: int = 3) -> pd.DataFrame:
        """Analyze stocks based on a custom strategy."""
        if threshold > obs_days:
            raise ValueError("threshold should be less than obs_days!")
        if current_date == 'today':
            current_date = self.get_current_date()

        df = self.calculate(current_date=current_date, obs_days=obs_days)
        df['flag'] = np.where(((df['放缩'] == '放') & (df['涨跌'] == '涨')) | 
                              ((df['放缩'] == '缩') & (df['涨跌'] == '跌')) | 
                              ((df['放缩'] == '缩') & (df['涨跌'] == '涨') & (df['是否涨停'] == '是')), 1, 0)

        tmp = df.groupby('ts_code').apply(lambda x: pd.Series({
            'index1': x['flag'].sum(),
            'index2': x['vol_change'].abs().max()
        }))
        return df.merge(tmp, on='ts_code', how='left')

    def _write_to_excel(self, df: pd.DataFrame, writer: pd.ExcelWriter, concept: str):
        """Helper function to write DataFrame to Excel."""
        startrow, startcol = 1, 1
        df = df.sort_values(by=['index1', 'index2'], ascending=[False, False])
        codes = df['ts_code'].unique().tolist()
        safe_concept = re.sub(r'[\/:*?"<>|]', '_', concept)

        for code in codes:
            df_code = df[df['ts_code'] == code]
            df_code.to_excel(writer, sheet_name=safe_concept, startrow=startrow, startcol=startcol, index=None)
            startrow += df_code.shape[0] + 3

    def report(self, my_strategy, file_name: str = 'nope', **kwargs):
        """Generate a report based on the given strategy."""
        df = my_strategy(**kwargs)
        if file_name == 'nope':
            file_name = datetime.now().strftime("%Y%m%d")

        with pd.ExcelWriter(f'./{file_name}.xlsx') as writer:
            for concept in df['概念'].unique():
                self._write_to_excel(df[df['概念'] == concept], writer, concept)
