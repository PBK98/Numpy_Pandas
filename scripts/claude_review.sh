#!/usr/bin/env bash
# Codex가 코드 변경 후 호출하는 Claude 리뷰 (작업당 1회)
# 사용법: scripts/claude_review.sh [비교기준]   (기본: HEAD = 아직 커밋 안 한 변경분)
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
BASE="${1:-HEAD}"
OUT_DIR=".review"
mkdir -p "$OUT_DIR"
DIFF_FILE="$OUT_DIR/review.diff"
OUT_FILE="$OUT_DIR/claude_review.md"

command -v claude >/dev/null || { echo "claude CLI를 찾을 수 없습니다." >&2; exit 1; }

# 수정된 파일 diff (노트북 JSON은 너무 길어서 따로 처리)
git diff "$BASE" -- . ':(exclude)*.ipynb' > "$DIFF_FILE"

# 새로 추가된(추적 안 되는) 파일도 포함
for f in $(git ls-files --others --exclude-standard -- . ':(exclude)*.ipynb' ':(exclude).review'); do
  echo "=== 새 파일: $f ===" >> "$DIFF_FILE"
  cat "$f" >> "$DIFF_FILE"
done

# 변경된 노트북은 파일명만 알려주고 Claude가 직접 읽게 함
NOTEBOOKS=$( { git diff --name-only "$BASE" -- '*.ipynb'; git ls-files --others --exclude-standard -- '*.ipynb'; } | sort -u )

if [ ! -s "$DIFF_FILE" ] && [ -z "$NOTEBOOKS" ]; then
  echo "변경 사항 없음 - 리뷰 생략"
  exit 0
fi

claude -p "너는 코드 리뷰어다. 아래 변경 사항을 검토하라. 필요하면 저장소의 파일을 직접 읽어 맥락을 확인하라.
- 버그, 엣지 케이스(NaN/빈 DataFrame/dtype/인덱스 정렬 등), 성능 문제, 테스트 누락만 지적하라. 스타일 취향은 제외.
- 각 항목: [심각도: 높음/중간/낮음] 파일:라인 - 문제 / 근거 / 수정 제안
- 문제가 없으면 '이상 없음'이라고만 써라.
- 코드를 직접 수정하지 마라. 한국어로 답하라.

[변경된 노트북 - 필요하면 직접 읽을 것]
${NOTEBOOKS:-없음}

[diff]
$(cat "$DIFF_FILE")" \
  --allowedTools "Read,Grep,Glob" \
  > "$OUT_FILE"

cat "$OUT_FILE"
