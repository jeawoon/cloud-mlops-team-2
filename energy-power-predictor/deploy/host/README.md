# 상시 로그 수집과 main 자동 배포

사용자가 승인한 기존 yeonsung-ec2-cloudwatch-role을 EC2에 연결한 뒤 `bash deploy/host/install.sh`로 설치합니다. 새 IAM 역할/액세스 키, SSH 인바운드 확대는 필요하지 않습니다. 이 역할에는 AWS 표준 CloudWatchAgentServerPolicy가 있어 두 그룹 외 권한도 존재하지만 에이전트 설정에는 지표 수집을 넣지 않았습니다.

- energy-log-bridge.timer: 15초마다 SQLite 평가 이벤트와 blue/green 컨테이너 출력을 고정 파일로 수집합니다. CloudWatch Agent가 /energy-predictor/api 및 /energy-predictor/web의 인스턴스 ID 스트림으로 전송합니다.
- SQLite가 원본이며 checkpoint 갱신 전에 파일 append/fsync를 수행합니다. 재시도나 장애 시 event_id 중복이 생길 수 있으므로 재학습 추출 시 중복 제거합니다. 라벨 없는 기록과 테스트 이벤트, 삭제 표시 기록은 학습에 쓰지 않습니다. 수집 로그는 로컬에서 일별/10MB 기준 최대14개 회전 보관합니다. CloudWatch 보관 기간은 별도 그룹 설정을 따릅니다.
- energy-auto-deploy.timer: 5분마다 공개 GitHub 저장소 main을 조회하고 해당 SHA에 대한 push용 Appliance simulator tests workflow가 최신 실행에서 성공한 경우만 배포합니다. main 이동을 재확인하고 SHA로 고정된 소스를 HTTPS로 내려받아 블루·그린 배포합니다. 성공한 SHA는 저장해 재배포를 피합니다. systemd와 기존 flock으로 중복 실행을 막습니다.
- GitHub Actions의 SSH deploy job은 비활성 상태로 유지합니다. 실제 배포 주체는 EC2 timer이며 GitHub Actions는 테스트 게이트 역할입니다. 저장소가 비공개로 바뀌면 조회가 실패하고 배포하지 않습니다. main 변경 권한을 가진 사람의 코드가 서버에서 실행되는 구조입니다.

확인:

```bash
systemctl list-timers 'energy-*' --no-pager
sudo journalctl -u energy-auto-deploy -n 40 --no-pager
sudo journalctl -u energy-log-bridge -n 20 --no-pager
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a status
```

일시 중지:

```bash
sudo systemctl stop energy-auto-deploy.timer
sudo systemctl stop energy-log-bridge.timer amazon-cloudwatch-agent
```

현재 실행 중인 배포를 중지하려면 서비스 상태와 Nginx 연결을 먼저 확인해야 합니다. timer를 중지해도 이미 실행 중인 서비스는 계속될 수 있습니다. 요금은 기존 EC2 및 CloudWatch 사용량에 따라 발생합니다. 재학습은 실행하지 않습니다.
