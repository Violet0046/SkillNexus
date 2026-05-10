---
name: json-to-monthly-csv-report
description: Transforms raw JSON data into a summarized monthly CSV report with accompanying visualizations.
---

**Purpose:** This skill outlines a reusable workflow for processing JSON datasets, performing monthly time-based aggregations, and generating a clean CSV report along with summary charts.

**Guiding Principle:** Prioritize clarity, data validation, and creating outputs that are immediately useful for analysis.

### Workflow

#### Phase 1: Preparation & Validation
1.  **Inspect the Source Data:**
    *   Check the size and structure of the input JSON file. For large files, consider a streaming parser (e.g., `ijson`) to manage memory.
    *   Identify the key fields: the date/time field (e.g., `order_date`, `timestamp`) and the numeric metric to aggregate (e.g., `sales_amount`, `quantity`).
    *   Ensure the date field is parseable into a standard datetime format.

#### Phase 2: Data Processing & Aggregation
2.  **Create a Python Script (e.g., `process_report.py`):**
    *   **Import Libraries:** Use `pandas` for data handling and aggregation, `json` or `ijson` for reading, and `matplotlib`/`seaborn` for plotting.
    *   **Load and Transform Data:**
        *   Read the JSON data into a DataFrame.
        *   Convert the date column to datetime objects using `pd.to_datetime()`.
        *   Create a new `year_month` column (e.g., `df['year_month'] = df['date'].dt.to_period('M')`).
    *   **Compute Aggregations:**
        *   Group the data by `year_month`.
        *   Calculate the desired summaries (e.g., `.sum()`, `.mean()`, `.count()`).
        *   Pivot or reshape the result for clarity if needed.

#### Phase 3: Output Generation
3.  **Generate the CSV Report:**
    *   Save the aggregated DataFrame to a CSV file (e.g., `monthly_summary.csv`). Include a clear header.
    *   Consider also exporting the cleaned, raw data with the `year_month` column added as a separate file for drill-down analysis.
4.  **Create Visualizations:**
    *   Generate at least one plot that tells a clear story (e.g., a bar chart of monthly totals, a line chart showing trends).
    *   Label axes clearly (e.g., "Month", "Total Sales ($)") and add a descriptive title.
    *   Save the plot(s) as a PNG or PDF file (e.g., `monthly_trend.png`).

### Generalization Tips
*   **Parameterize:** Design the script to accept input/output paths and column name mappings as arguments or variables at the top.
*   **Handle Errors:** Include try-except blocks for file I/O, date parsing, and potential missing data.
*   **Scalability:** For very large datasets, process data in chunks and use incremental aggregation.
*   **Reusability:** The core logic (groupby, aggregation, CSV export, plotting) can be adapted to any time-series JSON data by swapping column names and aggregation functions.

**Final Output:** The successful execution produces three key artifacts:
1.  A clean, aggregated `monthly_summary.csv`.
2.  One or more explanatory charts.
3.  A Python script that documents the entire transformation pipeline.