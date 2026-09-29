from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.release_check import release_findings


def main() -> int:
    tracked: list[str] = []
    if (ROOT / ".git").exists():
        completed = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if completed.returncode != 0:
            print(completed.stderr.strip() or "git ls-files failed")
            return 1
        tracked = [line for line in completed.stdout.splitlines() if line]
    findings = release_findings(ROOT, tracked)
    if findings:
        print("交付检查未通过：")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("交付检查通过：端口只发布到本机，调查数据不进 Git 和镜像，前端许可与 EULA 一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
