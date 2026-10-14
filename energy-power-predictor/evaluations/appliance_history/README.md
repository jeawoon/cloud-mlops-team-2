# Appliance-channel experiment

Source: REFIT cleaned data, https://zenodo.org/records/5063428 (CC-BY-4.0).
Raw file checksums are verified before training. Files are not modified.

Adds 45 features to the 31-feature long aggregate-history model: each of nine
house-specific appliance channels contributes current/previous 10-minute Wh,
past-hour mean, change, and an activity proxy (mean power greater than 20 W).
The activity threshold is a heuristic, not a measured switch state. Channel
numbers are not appliance labels and must not be interchanged between houses.

Each house is trained independently. Both feature sets use identical complete
samples, chronological 60/20/20 splits, and target-boundary embargo. Three
tree-size candidates are chosen by validation R², then refit on train+validation.
No future appliance reading is used. These previously inspected final periods
are not a new blind test; independent future-data confirmation remains needed.

| House | Horizon | Aggregate only R² | With appliances R² | Test samples |
|---|---|---:|---:|---:|
| House11 | 10 minutes | 0.8646 | 0.8657 | 5,853 |
| House11 | 60 minutes | 0.8648 | 0.8607 | 5,694 |
| House2 | 10 minutes | 0.4809 | 0.5720 | 11,674 |
| House2 | 60 minutes | 0.5468 | 0.6060 | 11,609 |

The baseline here is HOUSE-SPECIFIC, unlike the prior pooled model. Do not
attribute the entire change from prior pooled results to appliance features.
House11 exceeds 0.85 but this is not a general-home score. French household data
is excluded because it lacks the matching nine-channel measurements.

Run: `.venv/bin/python train_appliance_history.py`.
Saved bundle: `models/appliance_history_model.joblib`.
Inference: `predict_appliance_history(readings, house, minutes=60)` in
`train_appliance_history.py`. Readings must be a unique timestamp-indexed
DataFrame of 10-minute Wh for Aggregate and Appliance1..9, spanning at least
7 days plus one reading. House must be CLEAN_House11 or CLEAN_House2 with the
original channel mapping. Output is average Wh per 10 minutes; multiply by six
for total hourly Wh. Only completed bins available at the forecast origin belong
in the input. This is not wired to the existing six-reading web demo or deployed
to AWS; those interfaces cannot supply the necessary channel history.
