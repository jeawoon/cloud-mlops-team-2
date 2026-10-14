"""Human-readable actual/predicted examples using the real prediction API."""
import json
import streamlit as st
from src.verification import load_cases


def render_verification(request_prediction):
    with st.expander('검증용 예제: 실측 정답과 예측 비교', expanded=False):
        st.write('예제를 선택하고 실행한 뒤 입력·예측 범위·실제값·오차를 직접 확인하세요.')
        st.caption('산식 확인과 실측 테스트를 구분합니다. 이 예제의 오차로 전체 정확도를 판단하지 않습니다.')
        try:
            fixture = load_cases()
        except (OSError, ValueError, KeyError, RuntimeError):
            st.error('검증 예제 파일 또는 모델 버전을 확인하세요.')
            return
        cases = {c['id']: c for c in fixture['cases']}
        selected = st.selectbox('검증 예제 선택', list(cases),
                                format_func=lambda key: cases[key]['label'], key='verification_case')
        case = cases[selected]
        st.caption(f"범위: {case['scope']} · 선택 규칙: {case['selection_rule']}")
        with st.expander('API에 보내는 입력값'):
            st.json(case['payload'])
        if st.button('검증 예제 예측 실행', key='verification_run'):
            st.session_state.verification_result = request_prediction('/api/verification', {'case_id': selected})
        result = st.session_state.get('verification_result')
        if not result or result['case_id'] != selected:
            return
        a, b, c = st.columns(3)
        a.metric('산식 정답 (Wh)' if result['kind'] == 'formula' else '실측 정답 (Wh)', f"{result['actual_wh']:.3f}")
        b.metric('프로그램 예측 (Wh)', f"{result['predicted_wh']:.3f}")
        c.metric('절대오차 (Wh)', f"{result['absolute_error_wh']:.3f}")
        st.write(f"예상 추가요금: {result['predicted_cost_krw']:.2f}원 · 정답 에너지의 동일 단가 환산: {result['actual_energy_equivalent_cost_krw']:.2f}원")
        if result['relative_error_pct'] is None:
            st.caption('정답 0Wh이므로 상대오차는 계산하지 않습니다.')
        else:
            st.caption(f"이 예제의 상대오차: {result['relative_error_pct']:.2f}% (적중률이나 전체 R² 아님)")
        if result['reproduction_ok']:
            st.info('저장된 모델 출력 재현: 일치. 실측 정답을 정확히 맞혔다는 판정은 아닙니다.')
        else:
            st.warning('저장된 모델 출력과 다릅니다. 모델·입력·런타임 버전을 확인하세요.')
        st.caption(result['note'])
        st.write('출처:', result['source'])
        st.caption(f"원본 식별자/예측 시점: {result['record']}")
        checked = st.checkbox('입력값·예측 범위·실제값·오차를 직접 확인했습니다', key='human_check_'+selected)
        report = dict(result, human_confirmation=checked,
                      human_confirmation_note='이 브라우저 사용자의 체크 상태이며 팀원 PR 리뷰 승인이 아닙니다.')
        st.download_button('검증 결과 JSON 내려받기', json.dumps(report, ensure_ascii=False, indent=2),
                           file_name=selected+'-verification.json', mime='application/json')
        st.caption(fixture['note'])
