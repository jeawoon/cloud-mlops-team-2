# 운영 배포 준비 (아직 AWS에 적용하지 않음)

코드에는 bounded worker 8개, IP 기준 API 요청 제한, 선택적 서비스 토큰, 요청 본문/토큰을 제외한 상태·응답시간 로그, 컨테이너 healthcheck, 버전별 이미지 복구 경로를 추가했습니다. 기본 API는 loopback만 허용합니다.

## 외부에서 준비할 항목

1. 사용 권한이 있는 도메인과 DNS 관리 권한. 도메인의 A 레코드를 배포 서버에 연결합니다.
2. EC2 현재 주소·SSH 접속, 보안 그룹 HTTP 80·HTTPS 443. SSH는 내 IP만 허용합니다.
3. 고정 주소가 필요하면 AWS Elastic IP를 비용 확인 후 별도 할당합니다. 이 작업은 앱 코드로 완료되지 않습니다.
4. Docker/Compose 설치 및 기존 Nginx와 80/443 포트 충돌 해결 계획. 기존 Nginx를 확인 없이 중지하지 마세요.
5. 실제 기록이 저장된 디스크의 접근 통제·암호화·백업·보존 기간 정책.

`env.example`은 예시이며 실제 도메인·무작위 토큰을 넣은 `deploy/local.env`는 Git에서 제외합니다. 컨테이너는 기본 플레이스홀더 토큰으로 시작하지 않습니다. 토큰은 앱과 내부 API가 공유하며 사용자 기록 접근 키와 다릅니다.

조건이 준비된 서버에서 프로젝트 폴더 기준으로:

```bash
docker compose --env-file deploy/local.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/local.env -f deploy/compose.yaml build app
docker compose --env-file deploy/local.env -f deploy/compose.yaml up -d --wait
docker compose --env-file deploy/local.env -f deploy/compose.yaml ps
```

Compose config 전체 출력에는 비밀값이 포함될 수 있으므로 `--quiet`를 사용하세요. Caddy는 유효한 DNS·도메인 소유·포트 조건이 충족돼야 인증서를 발급받습니다. 아직 HTTPS가 설정됐다고 간주하지 마세요. IP 주소로 접속하거나 경고를 무시하는 방식으로 인증서를 대체하지 않습니다.

API 8000과 UI 8501은 호스트에 직접 공개하지 않습니다. Caddy는 `/api/*`를 차단하고 웹만 프록시합니다. 앱의 파일 업로드는 최대 2MB이며 서버에 원본 CSV를 저장하지 않습니다. 기록은 동의 후 이름·입력·모델 버전·예측·사용자가 입력한 실측만 로컬 SQLite volume에 저장합니다. 브라우저별 비밀 접근 키 분리는 계정 인증을 대체하지 않습니다. 인터넷 운영에는 HTTPS와 추가 계정 인증을 권장합니다.

## 장애 확인과 복구

- `docker compose ... ps`, `logs --tail 100 app`으로 상태와 응답 코드/시간을 확인합니다. `...`는 위의 동일한 env/file 옵션입니다.
- 로그에는 입력 본문·토큰을 넣지 않았지만 운영자가 로그·백업 접근 권한도 관리해야 합니다.
- 배포 전 현재 `ENERGY_IMAGE` 태그와 Git 커밋을 기록하고 이전 이미지를 보존합니다. 문제 시 env의 이미지 태그를 이전 검증 버전으로 되돌린 후 `up -d --no-build --wait app`을 실행합니다.
- SQLite schema가 다른 버전으로 되돌아갈 때는 호환성을 확인하세요. 데이터 volume을 자동 삭제하지 않습니다. `down -v`를 복구 명령으로 쓰지 마세요.
- healthcheck 실패 알림은 모니터링 도구에 연결해야 하며 자동 재배포·장애 알림·Elastic IP·실제 DNS 설정은 이 코드 추가만으로 활성화되지 않습니다.

참고: https://caddyserver.com/docs/automatic-https
