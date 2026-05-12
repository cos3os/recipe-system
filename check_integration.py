import os
import sys

print("🔍 [시스템 통합 충돌 테스트 시작]\n")

# 1. 프론트엔드(네가 만든 파일) 임포트 확인
print("1. 프론트엔드 모듈(core) 확인 중...")
try:
    from core import scaling, kg_query
    print("  ✅ core 모듈(scaling, kg_query) 정상 임포트 완료")
except Exception as e:
    print(f"  ❌ core 모듈 오류 (이름 다름/파일 없음): {e}")

# 2. 백엔드(팀원이 만든 DB) 연결 및 변수명 확인
print("\n2. 데이터베이스(app.database) 연결 및 테이블 확인 중...")
try:
    # app/database.py 안에 SessionLocal, User, FridgeStock 클래스가 제대로 있는지 확인
    from app.database import SessionLocal, User, FridgeStock
    
    db = SessionLocal()
    user_count = db.query(User).count()
    fridge_count = db.query(FridgeStock).count()
    
    print(f"  ✅ DB 연결 성공! (조회된 User: {user_count}명, FridgeStock: {fridge_count}개)")
    db.close()
except ImportError as e:
    print(f"  ❌ 변수명 충돌/임포트 오류: {e} (database.py 안에 해당 클래스 이름이 다를 수 있음)")
except Exception as e:
    print(f"  ❌ DB 실행 오류: {e}")

# 3. 주방장(LP 엔진) 접근 가능 여부 확인
print("\n3. LP 엔진 모듈 확인 중...")
try:
    # app/lp 폴더가 파이썬 모듈로 잘 읽히는지 확인
    from app import lp
    print("  ✅ LP 엔진 폴더 인식 완료")
    
    # LP 엔진 안에 어떤 함수들이 들어있는지 출력해보기
    import inspect
    import pkgutil
    modules = [name for _, name, _ in pkgutil.iter_modules(lp.__path__)]
    print(f"  ✅ LP 폴더 내부 파일: {modules}")
    
except Exception as e:
    print(f"  ❌ LP 엔진 접근 오류: {e}")

print("\n🎯 [테스트 종료]")
print("결과에 '❌' 표시가 뜬다면, 변수명이나 파일 위치가 안 맞는 것입니다.")