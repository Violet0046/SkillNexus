---
name: csv-report-broken-enhanced
---
**Part 1** — CHANGE_SUMMARY: Creates a comprehensive Python data analysis workflow skill that expands from basic CSV reporting to include multi-format data ingestion, cleaning, visualization, and formatted report generation.

**Part 2** — Actual changes (Format B: full rewrite):

---
name: python-data-analysis-pipeline
description: 完整的 Python 数据分析报告生成工作流，包含多格式数据读取、pandas 数据清洗、统计分析、matplotlib 可视化及报告输出
---

# Python 数据分析报告生成工作流

## 完整流程概览

1. **数据获取与读取**
2. **数据清洗与预处理**
3. **探索性数据分析 (EDA)**
4. **统计分析与聚合**
5. **数据可视化**
6. **报告格式化与输出**

## 步骤详解

### 1. 数据读取

```python
import pandas as pd
import json

# 从不同格式读取数据
def load_data(file_path, file_type='auto'):
    """支持多种格式的数据读取"""
    try:
        if file_type == 'auto':
            # 自动检测文件类型
            if file_path.endswith('.csv'):
                return pd.read_csv(file_path, encoding='utf-8-sig')
            elif file_path.endswith('.xlsx') or file_path.endswith('.xls'):
                return pd.read_excel(file_path, engine='openpyxl')
            elif file_path.endswith('.json'):
                return pd.read_json(file_path, encoding='utf-8-sig')
            else:
                # 尝试作为 CSV 读取
                return pd.read_csv(file_path, encoding='utf-8-sig')
        elif file_type == 'csv':
            return pd.read_csv(file_path, encoding='utf-8-sig')
        elif file_type == 'excel':
            return pd.read_excel(file_path, engine='openpyxl')
        elif file_type == 'json':
            return pd.read_json(file_path, encoding='utf-8-sig')
    except Exception as e:
        print(f"读取文件错误: {e}")
        return None
```

### 2. 数据清洗与预处理

```python
def clean_data(df):
    """常见的数据清洗操作"""
    df_clean = df.copy()
    
    # 处理缺失值
    df_clean = df_clean.dropna()  # 或 df_clean.fillna(0)
    
    # 删除重复行
    df_clean = df_clean.drop_duplicates()
    
    # 处理异常值（示例：去除极端值）
    numeric_cols = df_clean.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        Q1 = df_clean[col].quantile(0.25)
        Q3 = df_clean[col].quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        df_clean = df_clean[(df_clean[col] >= lower_bound) & 
                          (df_clean[col] <= upper_bound)]
    
    # 数据类型优化
    for col in df_clean.columns:
        if df_clean[col].dtype == 'object':
            # 尝试转换为数值
            try:
                df_clean[col] = pd.to_numeric(df_clean[col])
            except:
                pass
    
    return df_clean
```

### 3. 统计汇总

```python
def analyze_data(df, group_by_cols=None, agg_funcs=None):
    """灵活的数据分析与聚合"""
    
    # 默认聚合函数
    if agg_funcs is None:
        agg_funcs = ['mean', 'sum', 'count', 'min', 'max']
    
    # 基础统计
    stats = df.describe(include='all')
    
    # 分组统计
    if group_by_cols:
        group_stats = df.groupby(group_by_cols).agg(agg_funcs)
        return stats, group_stats
    
    return stats, None
```

### 4. 数据可视化

```python
import matplotlib.pyplot as plt
import seaborn as sns

def create_visualizations(df, columns=None):
    """创建多种类型的可视化图表"""
    
    plt.style.use('seaborn-v0_8')  # 设置美观的样式
    figures = {}
    
    if columns is None:
        columns = df.columns.tolist()
    
    # 1. 直方图（数值分布）
    numeric_cols = df.select_dtypes(include=[np.number]).columns[:3]  # 取前3个数值列
    if len(numeric_cols) > 0:
        fig, axes = plt.subplots(1, len(numeric_cols), figsize=(5*len(numeric_cols), 4))
        if len(numeric_cols) == 1:
            axes = [axes]
        for i, col in enumerate(numeric_cols):
            axes[i].hist(df[col].dropna(), bins=20, alpha=0.7)
            axes[i].set_title(f'{col} 分布')
        plt.tight_layout()
        figures['histogram'] = plt.gcf()
    
    # 2. 相关性热力图
    numeric_df = df.select_dtypes(include=[np.number])
    if len(numeric_df.columns) > 1:
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.heatmap(numeric_df.corr(), annot=True, cmap='coolwarm', ax=ax)
        plt.title('变量相关性矩阵')
        figures['heatmap'] = plt.gcf()
    
    # 3. 分组对比柱状图（示例）
    if 'category' in df.columns and len(numeric_df.columns) > 0:
        fig, ax = plt.subplots(figsize=(10, 6))
        df.groupby('category')[numeric_df.columns[0]].mean().plot(kind='bar', ax=ax)
        plt.title(f'按分类的 {numeric_df.columns[0]} 平均值')
        plt.xticks(rotation=45)
        figures['bar_chart'] = plt.gcf()
    
    return figures
```

### 5. 报告格式化输出

```python
def generate_report(df, stats, group_stats=None, figures=None, 
                   output_format='text', filename='analysis_report'):
    """生成多种格式的报告"""
    
    if output_format == 'text':
        # 文本格式报告
        report_text = f"数据分析报告\n{'='*50}\n\n"
        report_text += f"数据集概况: {df.shape[0]} 行 × {df.shape[1]} 列\n\n"
        report_text += "基础统计:\n"
        report_text += stats.to_string() + "\n\n"
        
        if group_stats is not None:
            report_text += "分组统计:\n"
            report_text += group_stats.to_string() + "\n\n"
        
        # 保存文本报告
        with open(f'{filename}.txt', 'w', encoding='utf-8') as f:
            f.write(report_text)
        
        return report_text
    
    elif output_format == 'html':
        # HTML 格式报告
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>数据分析报告</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <h1>数据分析报告</h1>
            <h2>数据集概况</h2>
            <p>行数: {df.shape[0]}, 列数: {df.shape[1]}</p>
            
            <h2>基础统计</h2>
            {stats.to_html()}
        """
        
        if group_stats is not None:
            html_content += f"""
            <h2>分组统计</h2>
            {group_stats.to_html()}
            """
        
        html_content += """
        </body>
        </html>
        """
        
        with open(f'{filename}.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return html_content
    
    # 保存图表
    if figures:
        for name, fig in figures.items():
            fig.savefig(f'{filename}_{name}.png', dpi=300, bbox_inches='tight')
            plt.close(fig)
```

## 完整使用示例

```python
# 主工作流函数
def full_analysis_pipeline(data_path, group_cols=None, output_format='text'):
    """完整的分析流程"""
    
    # 1. 加载数据
    df = load_data(data_path)
    if df is None:
        return
    
    # 2. 数据清洗
    df_clean = clean_data(df)
    
    # 3. 统计分析
    stats, group_stats = analyze_data(df_clean, group_by_cols=group_cols)
    
    # 4. 可视化
    figures = create_visualizations(df_clean)
    
    # 5. 生成报告
    report = generate_report(
        df_clean, stats, group_stats, figures, 
        output_format=output_format
    )
    
    print("分析完成！报告已保存。")
    return df_clean, stats, report

# 使用示例
if __name__ == "__main__":
    # 示例：分析销售数据
    df, stats, report = full_analysis_pipeline(
        'sales_data.csv', 
        group_cols=['product_category'],
        output_format='html'
    )
```

## 常见错误处理

### 1. 数据读取问题
```python
# 解决编码问题
try:
    df = pd.read_csv('data.csv', encoding='utf-8-sig')
except UnicodeDecodeError:
    df = pd.read_csv('data.csv', encoding='gbk')

# 解决大数据集内存问题
chunk_size = 10000
chunks = pd.read_csv('big_data.csv', chunksize=chunk_size)
df = pd.concat(chunks, ignore_index=True)
```

### 2. 内存优化
```python
# 优化数据类型减少内存使用
def optimize_memory(df):
    """优化DataFrame内存使用"""
    for col in df.columns:
        if df[col].dtype == 'float64':
            df[col] = df[col].astype('float32')
        elif df[col].dtype == 'int64':
            if df[col].min() >= 0:
                if df[col].max() < 255:
                    df[col] = df[col].astype('uint8')
                elif df[col].max() < 65535:
                    df[col] = df[col].astype('uint16')
            else:
                if df[col].max() < 127 and df[col].min() > -128:
                    df[col] = df[col].astype('int8')
                elif df[col].max() < 32767 and df[col].min() > -32768:
                    df[col] = df[col].astype('int16')
    return df
```

## 性能优化建议

1. **使用向量化操作**：避免使用循环，利用pandas内置函数
2. **适当使用索引**：对频繁查询的列设置索引
3. **分块处理大数据**：使用`chunksize`参数处理大文件
4. **并行处理**：使用`pandarallel`库加速应用函数
5. **及时释放内存**：处理完大对象后使用`del`和`gc.collect()`

## 注意事项

1. 始终检查数据质量，处理缺失值和异常值
2. 选择合适的图表类型展示数据关系
3. 报告要包含关键发现和业务建议
4. 定期备份原始数据和分析脚本
5. 注意数据隐私和安全合规要求