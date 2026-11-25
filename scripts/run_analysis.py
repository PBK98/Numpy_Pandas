"""프로젝트 루트에서 .venv/bin/python scripts/run_analysis.py (정상 실행 시 출력 없음)."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.reporting import run_analysis

if __name__=='__main__':
    run_analysis()
