"""웹페이지를 배포용 dist 폴더에 복사합니다. 추가 패키지 불필요."""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build():
    data = json.loads((ROOT / "data/jobs.json").read_text(encoding="utf-8"))
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    for name in ["index.html", "styles.css", "app.js"]:
        shutil.copy2(ROOT / "web" / name, dist / name)
    (dist / "data").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "data/jobs.json", dist / "data/jobs.json")
    # 로컬에서 HTML을 더블클릭해도 초기 데이터를 볼 수 있도록 포함합니다.
    embedded = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    (dist / "data.js").write_text("window.INITIAL_JOBS = " + embedded + ";\n", encoding="utf-8")
    (dist / ".nojekyll").touch()
    print(f"웹페이지 생성 완료: {dist / 'index.html'}")


if __name__ == "__main__":
    build()
