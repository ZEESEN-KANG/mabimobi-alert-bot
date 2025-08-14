import sys
from pathlib import Path

def get_app_dir() -> Path:
    if getattr(sys, 'frozen', False):
        # PyInstaller로 패키징된 경우
        return Path(sys._MEIPASS)
    else:
        # 일반 파이썬 실행일 경우: main.py 기준 경로
        return Path(sys.argv[0]).resolve().parent