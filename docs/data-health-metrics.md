# Data Health Metrics

## Purpose

Data health checks ensure that datasets are suitable for accurate backtesting. The focus is on **data quality** rather than quantity—specifically whether market data is complete enough to price trades correctly.

## Key Metrics

### 1. **Trades** (Total Trade Count)
- **What**: Total number of trades in the dataset
- **Why**: Indicates dataset size and activity level
- **Interpretation**: More trades = more robust backtest results

### 2. **Market Files**
- **What**: Number of market data files (tick data) available
- **Why**: Indicates coverage of market data across dates and pairs
- **Interpretation**: More market files = better pricing coverage
- **Note**: Trade books (e.g., MAD_GLD) and market pairs (e.g., EURUSD) are separate namespaces. The decrossing engine maps trades to available market data dynamically.

### 3. **Large Gaps** (Gaps > 5min)
- **What**: Number of time gaps exceeding 5 minutes in market data
- **Why Critical**: Large gaps can lead to:
  - Inaccurate pricing (stale quotes)
  - Missed trading opportunities
  - Unrealistic backtest results
- **Interpretation**:
  - `0` → Continuous data ✅
  - `> 0` → Data interruptions ⚠️

## Status Badges

### ✅ **Ready**
- No gaps > 5 minutes in market data
- Dataset is ready for backtesting with reliable pricing

### ⚠️ **Gaps Detected**
- Gaps > 5 minutes detected in market data
- **Action**: Review gap warnings below:
  - Evaluate impact on trading periods
  - Consider filling gaps or excluding affected periods
  - Accept limitations if gaps don't overlap critical trades

## Gap Analysis

Market data gaps affect pricing accuracy during those time periods. The health check identifies:
- **Gaps >1min**: May affect sub-minute trading strategies
- **Gaps >5min**: Likely to cause pricing inaccuracies (shown as warning)
- **Gaps >15min**: Major data interruptions requiring attention

### Gap Warning Details
Shows the severity distribution of time gaps in market data:
- **>1min gaps**: Minor gaps that may affect sub-minute precision
- **>5min gaps**: Significant gaps affecting pricing accuracy
- **>15min gaps**: Major data interruptions

**Action**: Review periods with large gaps, consider:
- Filling gaps from alternate data sources
- Excluding affected time periods from backtest
- Accepting limitations in affected periods

## Implementation Notes

### Where Health is Shown

**✅ Datasets Page** - Full health metrics for each dataset
- Shows: Trades, Market Coverage, Large Gaps
- Displays: Detailed warnings if issues exist
- Purpose: Dataset selection and quality assessment

**❌ Dashboard** - No health metrics
- Dashboard focuses on high-level inventory (datasets, pairs, files)
- Health is dataset-specific, not a global metric

### Backend Data

Health metrics computed by `DataHealthAnalyzer`:
- Uses DuckDB for efficient gap analysis
- Analyzes all pair-date combinations
- Summarizes gaps, coverage, and data availability

### API Endpoints

```
GET /api/v1/data-health?dataset={name}&validate_schemas={bool}
GET /api/v1/data-health/{dataset_name}?validate_schemas={bool}
```

Response includes:
- `summary.total_trades` - Trade count
- `summary.pairs_with_ticks` - Pairs with market data
- `summary.pairs_with_trades` - Pairs with trades
- `summary.gaps_over_1min` - Gap counts
- `summary.gaps_over_5min`otal trade count
- `summary.total_tick_files` - Number of market data files
- `summary.total_ticks` - Total tick count
- `summary.gaps_over_1min` - Count of gaps >1min
- `summary.gaps_over_5min` - Count of gaps >5min
- `summary.gaps_over_15min` - Count of gaps >15min
- `summary.pairs_with_ticks` - Unique market pairs with data
- `summary.pairs_with_trades` - Unique trade books with data