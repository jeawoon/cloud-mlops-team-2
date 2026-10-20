"""Appliance-specific electricity estimates; whole-house model removed."""
import json
import os
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import streamlit as st
from src.appliance_plan_ui import render_plan
from src.verification_ui import render_verification
from src.history_ui import render_history,save_controls

def request_prediction(endpoint,payload):
    url=os.environ.get('PREDICTION_API_URL','http://127.0.0.1:8000')+endpoint
    headers={'Content-Type':'application/json'}
    if os.environ.get('PREDICTION_API_TOKEN'):headers['Authorization']='Bearer '+os.environ['PREDICTION_API_TOKEN']
    request=Request(url,data=json.dumps(payload).encode(),headers=headers,method='POST')
    try:
        with urlopen(request,timeout=20) as response:return json.load(response)
    except HTTPError as error:
        if error.code in (401,422,429):
            try:st.error(json.load(error)['error'])
            except (ValueError,KeyError):st.error('입력값을 확인하세요.')
        else:st.error('예측 서버의 모델을 사용할 수 없습니다.')
        st.stop()
    except (OSError,ValueError):
        st.error('예측 서버에 연결할 수 없습니다. API 서버 실행 상태를 확인하세요.')
        st.stop()

st.set_page_config(page_title='가전별 예상 사용량·요금',page_icon='⚡',layout='centered')
page=st.radio('화면 선택',['간편 계산','AI 예측','내 기록'],horizontal=True,key='workspace_mode')
if page=='내 기록':render_history(request_prediction)
else:
    output=render_plan(request_prediction,'simple' if page=='간편 계산' else 'ai')
    if output is not None:save_controls(request_prediction,output[0])
    render_verification(request_prediction)
