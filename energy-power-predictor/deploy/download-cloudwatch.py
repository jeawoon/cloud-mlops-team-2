"""Run in an AWS CLI/CloudShell session with logs:FilterLogEvents permission.

python deploy/download-cloudwatch.py --out /tmp/cloudwatch-api.jsonl
Uses existing AWS credential chain; never copies keys into an artifact.
"""
import argparse
import json
from pathlib import Path
import time
import boto3

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--region',default='ap-northeast-2')
parser.add_argument('--group',default='/energy-predictor/api')
args=parser.parse_args()
client=boto3.client('logs',region_name=args.region)
end=int(time.time()*1000)
count=0
with args.out.open('w') as stream:
    args.out.chmod(0o600)
    for page in client.get_paginator('filter_log_events').paginate(logGroupName=args.group,endTime=end):
        for event in page['events']:
            stream.write(json.dumps(event,ensure_ascii=False)+'\n');count+=1
print(json.dumps(dict(group=args.group,region=args.region,end_time_ms=end,events=count)))
