import json
from typing import Any, Dict, Optional

class ConfigLoader:
    """
    Config.json 파일을 안전하게 읽어서 설정값을 반환하는 클래스

    예시:
        loader = ConfigLoader("/path/to/Config.json")
        config = loader.load()
        print(config["key"])
    """
    def __init__(self, config_path: str) -> None:
        """
        Args:
            config_path (str): 읽을 Config.json 파일 경로
        """
        self.config_path = config_path

    def load(self) -> Dict[str, Any]:
        """
        Config.json 파일을 읽어서 dict로 반환

        Returns:
            Dict[str, Any]: 설정값

        Raises:
            FileNotFoundError: 파일이 없을 때
            json.JSONDecodeError: JSON 문법 오류
        """
        try:
            with open(self.config_path, encoding="utf-8") as f:
                config = json.load(f)
            if not isinstance(config, dict):
                raise ValueError("Config.json의 최상위 구조는 dict여야 합니다.")
            return config
        except FileNotFoundError as e:
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {self.config_path}") from e
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(f"JSON 형식 오류: {e.msg}", e.doc, e.pos)
        except Exception as e:
            raise RuntimeError(f"설정 파일 로딩 실패: {e}") from e

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """
        특정 키의 값을 반환. 없으면 default 반환

        Args:
            key (str): 조회할 키
            default (Any, optional): 기본값

        Returns:
            Any: 설정값 또는 기본값
        """
        try:
            config = self.load()
            return config.get(key, default)
        except Exception:
            return default
