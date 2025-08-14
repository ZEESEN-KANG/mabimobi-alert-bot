import json
from typing import Dict, Set
from pathlib import Path

from module.utils import get_app_dir

CONFIG_PATH = get_app_dir() / "config"

def load_subscriptions(config_file_name: str) -> Dict[str, Set[int]]:
    """
    구독자 정보를 파일에서 로드하여 {구독타입: set(User ID)} 형태로 반환
    """
    file_path = CONFIG_PATH / config_file_name
    if not file_path.exists():
        return {"minute_5_before": set(), "minute_3_before": set(), "on_time": set(), "all": set()}
    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # set으로 변환
        return {k: set(v) for k, v in data.items()}
    except Exception:
        # 파일 구조 오류 등 예외
        return {"minute_5_before": set(), "minute_3_before": set(), "on_time": set(), "all": set()}

def save_subscriptions(config_file_name: str, data: Dict[str, Set[int]]) -> bool:
    """
    {구독타입: set(User ID)} 형태의 데이터를 파일로 저장
    """
    file_path = CONFIG_PATH / config_file_name
    try:
        # set → list 변환해서 저장
        serializable = {k: list(v) for k, v in data.items()}
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False