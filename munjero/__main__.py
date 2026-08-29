# -*- coding: utf-8 -*-
"""python -m munjero 진입점.

윈도우 콘솔은 기본 코드페이지가 cp949 라 한글 출력이 UnicodeEncodeError 로 죽는다.
bat 이 chcp 65001 을 하더라도 파이썬 쪽 스트림 인코딩을 따로 맞춰야 한다.
"""
import sys


def _force_utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_force_utf8()

from .cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
