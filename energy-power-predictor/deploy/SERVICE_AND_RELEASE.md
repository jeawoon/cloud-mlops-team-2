# 서비스 정의와 배포 확인

가정에서 가전을 사용하기 전에 전기 사용량을 계획하는 사용자가 가전 종류, 사용 시간, 지원되는 기기의 운전 조건을 입력하면 예상 사용 전력량과 추가 전기료를 확인하는 시뮬레이터입니다. 지원되는 학습 모델의 예측과 정격 소비전력 기반 계산은 구분하여 표시합니다. 예상 요금은 실제 청구서와 차이가 있을 수 있습니다.

## 구성

기존 EC2를 사용합니다. Nginx(80) → 호스트 loopback 8501 → Docker Compose app(Streamlit + 내부 API) → 모델/요금 계산 순서입니다. API 8000은 컨테이너 내부 전용입니다. 기록은 Compose의 고정 프로젝트 `energy-predictor`의 history volume에 보관합니다. 새 EC2/ECS/로드밸런서를 만들지 않습니다.

## 시작 전 확인

EC2의 Docker Engine/Compose, Nginx의 localhost:8501 프록시, Docker 실행 권한, sudo systemctl/nginx 권한이 필요합니다. 기존 기록 DB를 사용하는 경우 배포 전에 백업·이관해야 합니다. 이 스크립트는 이전 SQLite를 새 volume으로 자동 이관하지 않습니다.

비용과 서버 준비를 확인한 뒤 Repository variable `EC2_DEPLOY_ENABLED=true`로 배포를 활성화합니다. 그 전에는 배포 job이 건너뛰어집니다.

GitHub Settings → Environments → production에 EC2_HOST, EC2_USER, EC2_SSH_KEY, EC2_KNOWN_HOSTS secrets를 설정합니다. 키나 토큰을 Git에 넣지 마세요. KNOWN_HOSTS는 검증한 서버 host key를 사용합니다. SSH 22는 runner 접근이 가능해야 하며 임의로 전체 공개하지 않습니다. GitHub Actions 사용 가능량과 기존 AWS 비용을 확인하세요. 결제나 신규 유료 리소스가 필요하면 실행을 중단합니다.

## 배포

`.github/workflows/deploy-ec2.yml`은 main 변경 또는 수동 실행 시 테스트 후 해당 커밋을 서버로 복사하고 `deploy/deploy-ec2.sh`를 실행합니다. SSH 기반 배포이므로 AWS IAM 생성 권한은 필요하지 않습니다. 서버에 체크아웃이 있다면 `bash energy-power-predictor/deploy/deploy-ec2.sh`로도 실행할 수 있습니다.

GitHub concurrency와 서버 flock으로 동시 배포를 제한하고, 고정 Compose 프로젝트/서비스로 기존 컨테이너를 교체합니다. 이미지 빌드 성공 후 기존 systemd 앱을 중지합니다. 컨테이너 health 실패 시 기존 서비스를 다시 시작합니다. 최초 전환 후 시스템 서비스는 비활성화합니다. Nginx는 유지합니다. 배포 중 짧은 중단이 발생합니다. 이전 컨테이너 버전 자동 복구는 지원하지 않으므로 실패 시 이전 이미지 태그로 수동 복구해야 합니다.

## 검증 및 리뷰

1. Docker 이미지 안에서 unittest 7개 모듈 실행.
2. API와 Streamlit healthcheck 확인.
3. 화면의 동일한 검증 사례로 예측/API 응답 비교.
4. 로그에서 정상/잘못된 입력을 확인. 입력 본문/서비스 토큰을 공개하지 않음.
5. 배포 후 public /_stcore/health와 화면에서 실제 예측 확인.
6. 문구 변경 PR → CI 통과 → main 병합 → Actions 성공 → 서버 컨테이너 1개와 systemd 중복 실행 없음 확인.
7. 팀원이 PR Files changed와 검증 결과를 읽고 직접 리뷰. 리뷰 이전의 병합은 이 과제 순서에 맞지 않으므로 보류.

현재 EC2 접속 불가 상태에서는 외부 배포·중복 실행 검증·최종 모니터링 완료를 주장할 수 없습니다.
