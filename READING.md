# Quant learning path

A reading and viewing list for understanding how quant models for stocks are built, tested and judged. Work through it in order. Each step builds on the one before.

The goal is not to code every model yourself. It is to be able to tell a real edge from a lucky backtest.

## Step 1: Mindset (weeks 1–2)

1. **Fooled by Randomness** by Nassim Taleb. Most patterns that look like skill are luck. Read this before trusting any backtest.
2. **The Signal and the Noise** by Nate Silver. Why most forecasts fail, and how to tell signal from noise, with everyday examples.

## Step 2: Judging forecasts (weeks 3–4)

3. **Superforecasting** by Philip Tetlock and Dan Gardner. What it means for a forecast to be calibrated ("said 70%, happened 63%") and where the Brier score comes from. Thrive Alpha reports both.

## Step 3: The baseline you have to beat (weeks 5–6)

4. **A Random Walk Down Wall Street** by Burton Malkiel. Why prices are hard to predict and why index funds are hard to beat.
5. **The Little Book of Common Sense Investing** by John Bogle. Costs, and why SPY is the benchmark every BUY call has to beat.

## Step 4: How quant models are built and how they fail (weeks 7–10)

6. **Quantitative Trading, 2nd ed.** by Ernest Chan. Building and backtesting a simple strategy, and the classic traps: look-ahead bias, survivorship bias, overfitting and ignoring costs.
7. **Georgia Tech "Machine Learning for Trading" (CS 7646)** by Tucker Balch. Free lectures on YouTube. Build one small backtest in Python yourself while watching.
8. **Evidence-Based Technical Analysis** by David Aronson. How to test whether chart rules (support, resistance, patterns) really work. This is the method that showed support and resistance levels don't hold better than random prices.

## Step 5: What has worked over decades (weeks 11–12)

9. **Your Complete Guide to Factor-Based Investing** by Andrew Berkin and Larry Swedroe. Which return sources (value, momentum, quality, low volatility) have held up across markets and decades.

## Step 6: The model side (months 4–6)

10. **Machine Learning for Algorithmic Trading, 2nd ed.** by Stefan Jansen. Data, features, models and backtests, with Python code for every chapter (free on GitHub).
11. **Advances in Financial Machine Learning** by Marcos López de Prado. Purged cross-validation, "target or stop hit first" labels and backtest overfitting. Thrive Alpha uses these methods. Hard going but very useful.

## Step 7: Deeper theory (optional, months 6+)

12. **Active Portfolio Management** by Richard Grinold and Ronald Kahn. Measuring skill against a benchmark and sizing positions.
13. **MIT OpenCourseWare 18.S096, "Topics in Mathematics with Applications in Finance".** Free on YouTube. The probability and statistics underneath the models.
14. **Yale "Financial Markets" by Robert Shiller.** Free on Coursera. How markets behave and why bubbles happen.

## Two short papers

- **"The Probability of Backtest Overfitting"** by Bailey, Borwein, López de Prado and Zhu. Why the best backtest out of many is usually overfit.
- **"…and the Cross-Section of Expected Returns"** by Harvey, Liu and Zhu. Why most published stock signals don't hold up.

## Free data worth knowing about

- **Ken French Data Library:** decades of factor returns.
- **SEC EDGAR:** company filings.
- **FRED (St. Louis Fed):** macro data such as rates, inflation and unemployment.

## If you only have time for two

Ernest Chan's **Quantitative Trading** for the hands-on side, with the **Georgia Tech course** alongside it.

## Four questions to ask about any model result

1. Was it tested on data the model never saw?
2. How did it do against SPY, and against simply holding the stock?
3. How many cases is it based on?
4. Does it still work after costs and on bad market days?

Those four questions catch most bad models.
