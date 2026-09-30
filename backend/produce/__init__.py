"""제작(자막교체) 탭 — 2단계 A형 v1.

음악 + 화면 번인 영어 자막인 쇼츠를, 원본 음악·효과음은 그대로 두고 영어 자막을 가린 뒤
일본어 자막을 얹은 mp4로 만든다. 전부 로컬(ffmpeg + Claude 텍스트)로 처리한다.

기존 더빙 파이프라인(backend/pipeline/*)은 **읽어서 재사용만** 하고 수정하지 않는다:
- vision.extract / frames  → 번인 영어 자막 인식
- common.llm               → 일본어 자막 번역
- download.probe_media     → 해상도 확인
별도 저장소 data/produce/<id>/ 를 쓰며 기존 잡 스토어와 격리된다.
"""
