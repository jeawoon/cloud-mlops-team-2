# 서비스 정의와 배포 확인

가정에서 가전을 사용하기 전에 전기 사용량을 계획하는 사용자가 가전 종류, 사용 시간, 지원되는 기기의 운전 조건을 입력하면 예상 사용 전력량과 추가 전기료를 확인하는 시뮬레이터입니다. 지원되는 학습 모델의 예측과 정격 소비전력 기반 계산은 구분하여 표시합니다. 예상 요금은 실제 청구서와 차이가 있을 수 있습니다.

## 구성

기존 EC2를 사용합니다. Nginx(80) → 호스트 loopback 8501 → Docker Compose app(Streamlit + 내부 API) → 모델/요금 계산 순서입니다. API 8000은 컨테이너 내부 전용이며, UI가 서비스 토큰으로 호출합니다. EC2 Nginx의 기존 /api/ 프록시는 공개하지 않고 404로 바꿔야 합니다. API 직접 검증은 docker exec로 수행합니다. 기록은 Compose의 고정 프로젝트 `energy-predictor`의 history volume에 보관합니다. 새 EC2/ECS/로드밸런서를 만들지 않습니다.

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

## 2026-11-04 검증 결과

기존 EC2(13.124.57.226)에 Ubuntu 공식 Docker/Compose를 설치하고 PR 브랜치 c394f49를 배포했습니다. 로컬 Docker와 EC2 Docker에서 모델/API/화면 테스트 46개가 통과했습니다. 이미지/시작 검증 후 기존 systemd 서비스를 중지하고 자동 시작을 해제했습니다. Nginx의 /api/ 공개 경로는 백업 후 404로 전환했습니다. API는 UI 및 컨테이너 내부에서 호출합니다.

공개 웹 health 응답 ok, API 정상 200과 잘못된 case_id 422, API/직접 모델 결과 일치를 확인했습니다. 실제 웹 입력 100W·60분·200원/kWh에서 0.1000kWh·20.00원이 표시됐습니다. Docker 로그에서 요청 경로/상태/처리시간 기록을 확인했습니다.

GitHub Actions secrets/활성화 변수는 아직 설정하지 않았습니다. 자동 배포 성공이나 main 병합 후 배포 검증은 완료되지 않았습니다. 팀원의 실제 리뷰 후 병합해야 합니다. 새 AWS 리소스 생성이나 유료 요금제 결제는 하지 않았으며 기존 EC2 사용 요금은 별도입니다.

## 블루·그린 배포 (2026-11-04)

`deploy-ec2.sh`는 현재 Nginx upstream 8501/8502를 읽고 반대 포트의 `energy-blue` 또는 `energy-green` 프로젝트를 준비합니다. 활성 컨테이너는 새 이미지 테스트와 health 검사 동안 계속 실행됩니다. 검사 통과 후 nginx -t와 graceful reload로 연결을 전환하고 이전 컨테이너는 유지합니다. 전환/확인 실패 시 설정을 복원하고 후보 컨테이너만 중지합니다. 다음 배포에서는 비활성 슬롯을 재사용하므로 해당 슬롯의 오래된 연결은 종료될 수 있습니다. 최초 Docker 프로젝트의 컨테이너는 그 포트가 비활성일 때만 중지합니다.

두 슬롯이 같은 외부 history volume을 사용합니다. SQLite schema의 호환되지 않는 변경은 이 절차로 자동 처리하지 않습니다. Streamlit 기존 WebSocket은 이전 프로세스에서 유지될 수 있지만 전체 세션 무손실은 보장하지 않습니다. 후보 health는 모델/API와 UI health를 검사하며 모든 브라우저 상태를 검사하지 않습니다.

서버 메모리가 약 1GB이므로 최초 검증 시 기존 디스크에 1GB swap을 추가했습니다. 별도 인스턴스나 유료 리소스는 만들지 않았습니다. swap은 메모리 증설과 동등한 성능을 보장하지 않습니다.

터미널에서 커밋된 코드를 한 번에 업로드/배포:

```bash
EC2_HOST=13.124.57.226 EC2_KEY="$HOME/Downloads/energy-predictor-key.pem" bash deploy/upload-ec2.sh
```

위 명령은 `energy-power-predictor` 폴더에서 실행합니다. 최초 SSH host fingerprint를 확인하고 known_hosts에 등록해야 합니다. AWS CLI 자격증명과 DescribeInstances 권한이 있다면 EC2_HOST 대신 EC2_INSTANCE_ID를 지정해 현재 공인 IP를 조회할 수도 있습니다. 인스턴스 생성/시작이나 유료 옵션 변경은 하지 않습니다.

실측 기록: green(8502) 전환과 blue(8501) 재전환 모두 healthy를 확인했습니다. 두 번째 배포 중 외부 검사 40회 성공, 추가 실패 0회였습니다. 전체 기간에는 전환 전 Nginx 재시작과 겹친 연결 실패 2회가 있어 완전한 무중단을 보장하지는 않습니다.
