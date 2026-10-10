"""배포된 페이지와 데이터를 인증 헤더 없이 확인합니다."""
import json
import os
import time
from pathlib import Path
from urllib.request import urlopen

base = os.environ["PAGE_URL"]
expected = json.loads(Path("data/jobs.json").read_text())
for attempt in range(6):
    try:
        with urlopen(base, timeout=20) as response:
            assert response.status == 200
            assert "보건관리자 채용 모아보기" in response.read().decode()
        with urlopen(base + "data/jobs.json?t=" + str(time.time_ns()), timeout=20) as response:
            actual = json.load(response)
        assert actual == expected, "배포 데이터가 저장소 최신 데이터와 다릅니다"
        for asset in ["app.js", "styles.css", "data.js"]:
            with urlopen(base + asset, timeout=20) as response:
                assert response.status == 200 and response.read()
        print("익명 HTTP 200 · HTML/JS/CSS · 최신 데이터 일치 확인:", base)
        break
    except Exception:
        if attempt == 5:
            raise
        time.sleep(10)
