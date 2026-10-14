# Longer-history experiment

Run `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 .venv/bin/python train_long_history.py`.

Adds historical lags, 24-hour and 7-day rolling summaries, yesterday and last
week at the same time. Every input is available at or before the forecast
origin. Rolling summaries require 80% valid past readings. Missing required
lags/targets are excluded. Both baselines and extended models use identical
eligible samples and chronological 60/20/20 splits with target embargo.
Hyperparameters are selected on validation only; models are refit on training
plus validation. The final time period has been evaluated in prior experiments,
so these results still require confirmation on genuinely fresh future data.

| Forecast | Short-history R² | Long-history R² | Test samples |
|---|---:|---:|---:|
| Next 10 minutes, pooled normalized homes | 0.5757 | 0.5985 | 54,553 |
| Next 60 minutes, pooled normalized homes | 0.6402 | 0.6746 | 54,309 |
| House11 next 10 minutes | 0.8436 | 0.8507 | 5,853 |
| House11 next 60 minutes | 0.8251 | 0.8511 | 5,694 |

These are whole-house forecasts, not original UCI appliance-only forecasts.
The House11 result must not be presented as the pooled or general-home score.
The old published scores used more samples; compare only paired scores above.

Saved model: `models/long_history_model.joblib`.
Inference: `train_long_history.predict_history(history_wh, typical_wh, minutes)`
requires timestamped 10-minute Wh readings over at least 7 days plus one reading.
`typical_wh` must be a positive historical training-period household median.
Output is mean Wh per 10 minutes in the forecast horizon. For 60 minutes,
multiply by six to obtain hourly Wh. This model is not connected to the existing
six-reading web form, and the deployed model is unchanged.
