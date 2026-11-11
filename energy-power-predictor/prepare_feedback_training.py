"""Audit CloudWatch JSONL; export reviewed single-device labels, never invent targets.

Usage: python prepare_feedback_training.py input.jsonl --out reports/feedback
Optional --review review.json maps event IDs to explicit quality approval metadata.
Raw input/output labels belong outside Git. Only aggregate analysis may be published.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def prepare(lines, review=None):
    counts = Counter()
    latest = {}
    seen = set()
    review = review or {}
    for line in lines:
        counts['input_rows'] += 1
        try:
            value = json.loads(line)
            if isinstance(value, dict) and 'message' in value and 'event_type' not in value:
                value = json.loads(value['message'])
            if not isinstance(value, dict):
                raise ValueError('object required')
        except (ValueError, TypeError):
            counts['invalid_or_non_json'] += 1
            continue
        if value.get('event_type') not in ('prediction_saved', 'actual_recorded', 'record_deleted'):
            counts['operational_or_other'] += 1
            continue
        event_id, record_id = value.get('event_id'), value.get('prediction_id')
        try:
            timestamp = datetime.fromisoformat(value['occurred_at'].replace('Z', '+00:00'))
            if not timestamp.tzinfo or not isinstance(event_id, str) or not event_id or not isinstance(record_id, str) or not record_id:
                raise ValueError('missing event identity/timezone')
        except (KeyError, ValueError, TypeError, AttributeError):
            counts['invalid_feedback'] += 1
            continue
        # Wrapper metadata is not part of feedback identity; ingestion retries deduplicate.
        if event_id in seen:
            counts['duplicate_events'] += 1
            continue
        seen.add(event_id)
        counts['unique_feedback_events'] += 1
        key = (timestamp, event_id)
        if record_id not in latest or key > latest[record_id][0]:
            latest[record_id] = (key, value)
    rows = []
    for _, value in latest.values():
        if value.get('status') == 'deleted' or value['event_type'] == 'record_deleted':
            counts['deleted_records'] += 1
            continue
        target = value.get('target', {})
        if not isinstance(target, dict):
            counts['missing_or_invalid_actual'] += 1
            continue
        actual = target.get('actual_wh')
        if value.get('status') != 'evaluated' or not finite(actual) or not 0 <= actual <= 10000000:
            counts['missing_or_invalid_actual'] += 1
            continue
        counts['labeled_latest_records'] += 1
        inputs = value.get('inputs')
        plans = inputs.get('plans') if isinstance(inputs, dict) else None
        if not isinstance(plans, list) or len(plans) != 1 or not isinstance(plans[0], dict) or plans[0].get('quantity', 1) != 1 or plans[0].get('method') != 'recent_forecast' or plans[0].get('device') not in ('Appliance1', 'Appliance3'):
            counts['unsupported_scope'] += 1
            continue
        plan = plans[0]
        settings = plan.get('settings', {})
        if not isinstance(settings, dict):
            counts['invalid_or_unsupported_features'] += 1
            continue
        recent = settings.get('recent_wh')
        if settings.get('model_variant', 'standard') != 'standard' or not isinstance(recent, list) or len(recent) != 6 or not all(finite(v) and 0 <= v <= 4000/6 for v in recent) or actual > 4000/6:
            counts['invalid_or_unsupported_features'] += 1
            continue
        approval = review.get(value['event_id'], {})
        # Original records are user-reported and training_eligible=False. A human
        # must verify scope, household continuity, measurement and forecast time.
        try:
            forecast = datetime.fromisoformat(approval['forecast_at'].replace('Z', '+00:00'))
            if not forecast.tzinfo or approval.get('approved') is not True or not isinstance(approval.get('household_group'), str) or not approval['household_group'].strip() or approval.get('measurement_verified') is not True or approval.get('scope_verified') is not True:
                raise ValueError('quality review missing')
            if forecast > datetime.fromisoformat(value['occurred_at'].replace('Z', '+00:00')):
                raise ValueError('label precedes forecast')
            h, m, w = (settings.get(k, 0) for k in ('hour', 'minute', 'weekday'))
            if any(not finite(v) or int(v) != v for v in (h, m, w)) or not 0 <= h <= 23 or not 0 <= m <= 59 or not 0 <= w <= 6:
                raise ValueError('invalid calendar')
        except (KeyError, ValueError, TypeError, AttributeError):
            counts['quality_review_required'] += 1
            continue
        rows.append(dict(event_id=value['event_id'], forecast_at=forecast.isoformat(), household_group=approval['household_group'], device={'Appliance1':'fridge', 'Appliance3':'dishwasher'}[plan['device']], recent_wh=recent, hour=h, minute=m, weekday=w, actual_wh=actual))
    counts['reviewed_training_rows'] = len(rows)
    return sorted(rows, key=lambda r: datetime.fromisoformat(r['forecast_at'])), dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--review', type=Path)
    args = parser.parse_args()
    review = json.loads(args.review.read_text()) if args.review else {}
    with args.input.open() as stream:
        rows, counts = prepare(stream, review)
    args.out.mkdir(parents=True, exist_ok=True, mode=0o700)
    output = args.out/'reviewed_training.jsonl'
    output.write_text(''.join(json.dumps(r, ensure_ascii=False, allow_nan=False)+'\n' for r in rows))
    output.chmod(0o600)
    report = dict(source_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(), counts=counts,
                  retraining_status='blocked_no_reviewed_labels' if not rows else 'requires_temporal_split_and_independent_evaluation',
                  before_r2=None, after_r2=None, improvement=None,
                  note='Operational success is not prediction accuracy. No pseudo-labels, automatic approval, reinforcement learning, or model replacement.')
    (args.out/'analysis.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
