# PHP 풀스택 아키텍처

브라우저는 HTML/CSS/JavaScript로 구성하고 `/api` JSON 계약만 사용한다. PHP Front Controller가 보안 헤더, API Key, 업로드 검증과 응답 계약을 담당한다. `DatasetPipeline`은 DXF/STEP 파서, 정규화, SVG/PLY/JSON 생성, 품질 평가, Manifest 및 ZIP 패키징을 조정한다.

저장소는 PDO DSN으로 교체한다. 기본 로컬 실행은 SQLite이며 운영은 MySQL/MariaDB를 사용한다. SQL은 모두 Prepared Statement로 실행한다.

정밀 STEP B-Rep, Assembly, 물성 및 Mesh가 필요한 경우 PHP가 별도 OCP CAD Worker를 호출하되 job 상태와 Geometry/Manifest 계약은 유지한다.
