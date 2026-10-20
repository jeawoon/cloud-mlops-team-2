import json
import secrets
import streamlit as st


def token():
    if 'private_history_token' not in st.session_state:
        st.session_state.private_history_token=secrets.token_urlsafe(32)
    return st.session_state.private_history_token


def save_controls(request_prediction,payload):
    with st.expander('동의 후 이 예측을 기록으로 저장'):
        st.caption('자동 저장하지 않습니다. 동의하면 입력·모델 버전·예측을 이 서버 디스크에 저장합니다. CSV 파일 자체·계정·위치정보는 자동 수집하지 않습니다. 기록 이름에 개인정보를 입력하지 마세요. 접근 키를 잃으면 조회할 수 없으므로 결과와 비밀 복구키를 보관하세요.')
        label=st.text_input('기록 이름',value='선택 가전 계획',max_chars=80,key='record_label')
        consent=st.checkbox('해당 입력과 예측을 서버 디스크에 저장하는 데 동의합니다',key='record_consent')
        if st.button('이 예측 저장',disabled=not consent,key='save_prediction'):
            result=request_prediction('/api/records/save',dict(owner_token=token(),consent=consent,label=label,prediction_payload=payload))
            st.success('저장 완료: '+result['id'])


def render_history(request_prediction):
    st.header('내 예측·실측 기록')
    st.warning('현재 브라우저 세션의 기록만 조회합니다. 계정 로그인이 아니며 접근 키가 사라지면 복구할 수 없습니다. 배포 시 HTTPS가 필요합니다.')
    with st.expander('다시 접속할 때 쓸 비밀 복구키'):
        st.caption('복구키를 가진 사람은 이 기록을 조회·수정·삭제할 수 있습니다. 비밀번호처럼 보관하고 GitHub·채팅에 올리지 마세요. 파일은 암호화되지 않습니다.')
        st.download_button('기록 복구키 내려받기 (비밀 파일)',token(),file_name='private-history-access-key.txt',mime='text/plain')
        restore=st.text_input('보관한 복구키 입력',type='password',key='restore_history_key')
        if st.button('복구키 적용'):
            from src.history_store import owner_hash
            try:owner_hash(restore)
            except ValueError:st.error('복구키 형식을 확인하세요.')
            else:
                st.session_state.private_history_token=restore;st.rerun()
    response=request_prediction('/api/records/list',dict(owner_token=token()))
    rows=response['records']
    if not rows:
        st.info('저장한 기록이 없습니다. 계산 화면에서 저장에 동의한 뒤 저장 버튼을 누르세요.');return
    by_id={r['id']:r for r in rows}
    selected=st.selectbox('기록 선택',list(by_id),format_func=lambda key:by_id[key]['label']+' · '+by_id[key]['created'],key='history_selected')
    record=by_id[selected]
    st.write('예측 범위: ',[r['scope'] for r in record['prediction']['items']])
    st.metric('저장된 예측 Wh',f"{record['prediction']['selected_appliances_wh']:.3f}")
    if record['actual_wh'] is not None:
        a,b=st.columns(2);a.metric('실제 Wh',f"{record['actual_wh']:.3f}");b.metric('절대오차 Wh',f"{record['absolute_error_wh']:.3f}")
    actual=st.number_input('같은 범위의 실제 측정 사용량 (Wh)',min_value=0.,max_value=10000000.,value=float(record['actual_wh'] or 0),key='actual_'+record['id'])
    confirmed=st.checkbox('같은 가전·대수·예측 기간의 실측값입니다',key='scope_'+record['id'])
    if st.button('실측값 저장',disabled=not confirmed):
        request_prediction('/api/records/actual',dict(owner_token=token(),id=record['id'],actual_wh=actual,scope_confirmed=confirmed));st.rerun()
    st.download_button('내 기록 JSON 내려받기',json.dumps(rows,ensure_ascii=False,indent=2),file_name='my-predictions.json',mime='application/json')
    st.caption(response['note'])
    with st.expander('이 기록 삭제'):
        acknowledged=st.checkbox('이 기록을 삭제하면 앱에서 복구할 수 없음을 확인했습니다',key='delete_'+record['id'])
        if st.button('선택 기록 삭제',disabled=not acknowledged):
            request_prediction('/api/records/delete',dict(owner_token=token(),id=record['id'],confirm_delete=acknowledged));st.rerun()
