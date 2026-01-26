#!/usr/bin/env python3
"""
수신인 관리 CLI 도구

사용법:
  python scripts/manage_recipients.py add <email> <name>      # 수신인 추가
  python scripts/manage_recipients.py list                    # 전체 수신인 목록
  python scripts/manage_recipients.py list-active             # 활성 수신인 목록
  python scripts/manage_recipients.py remove <email>          # 수신인 삭제
  python scripts/manage_recipients.py unsubscribe <email>     # 수신거부 처리
  python scripts/manage_recipients.py resubscribe <email>     # 수신 재개
  python scripts/manage_recipients.py init                    # 초기 수신인 설정
"""
import os
import sys

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.recipients import RecipientManager


def print_recipient(recipient):
    """수신인 정보 출력"""
    print(f"  - {recipient.email:30s} | {recipient.name:10s} | {recipient.status.value:12s} | {recipient.created_at}")


def cmd_add(manager, email, name):
    """수신인 추가"""
    print(f"수신인 추가 중: {email} ({name})")
    if manager.add_recipient(email, name):
        print("✓ 추가 완료")
    else:
        print("✗ 추가 실패")


def cmd_list(manager):
    """전체 수신인 목록"""
    recipients = manager.get_all_recipients()
    print(f"\n전체 수신인 목록 ({len(recipients)}명):")
    print("=" * 80)
    for recipient in recipients:
        print_recipient(recipient)


def cmd_list_active(manager):
    """활성 수신인 목록"""
    recipients = manager.get_active_recipients()
    print(f"\n활성 수신인 목록 ({len(recipients)}명):")
    print("=" * 80)
    for recipient in recipients:
        print_recipient(recipient)


def cmd_remove(manager, email):
    """수신인 삭제"""
    print(f"수신인 삭제 중: {email}")
    if manager.delete_recipient(email):
        print("✓ 삭제 완료")
    else:
        print("✗ 삭제 실패")


def cmd_unsubscribe(manager, email):
    """수신거부 처리"""
    print(f"수신거부 처리 중: {email}")
    if manager.unsubscribe(email):
        print("✓ 수신거부 처리 완료")
    else:
        print("✗ 수신거부 처리 실패")


def cmd_resubscribe(manager, email):
    """수신 재개"""
    print(f"수신 재개 처리 중: {email}")
    if manager.resubscribe(email):
        print("✓ 수신 재개 완료")
    else:
        print("✗ 수신 재개 실패")


def cmd_init(manager):
    """초기 수신인 설정"""
    print("초기 수신인 설정 중...")

    # 초기 수신인 목록
    initial_recipients = [
        ("turtlesoup0@gmail.com", "관리자"),
        ("jjemoya@naver.com", "수신인1"),
        ("coolobj1.pe@gmail.com", "수신인2"),
        ("nalza10@naver.com", "수신인3"),
    ]

    result = manager.bulk_add_recipients(initial_recipients)

    print(f"\n결과:")
    print(f"  ✓ 성공: {result['success_count']}명")
    print(f"  ✗ 실패: {result['failed_count']}명")

    if result['failed_emails']:
        print(f"  실패 이메일: {', '.join(result['failed_emails'])}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    manager = RecipientManager()

    try:
        if command == "add":
            if len(sys.argv) < 4:
                print("사용법: python scripts/manage_recipients.py add <email> <name>")
                sys.exit(1)
            cmd_add(manager, sys.argv[2], sys.argv[3])

        elif command == "list":
            cmd_list(manager)

        elif command == "list-active":
            cmd_list_active(manager)

        elif command == "remove":
            if len(sys.argv) < 3:
                print("사용법: python scripts/manage_recipients.py remove <email>")
                sys.exit(1)
            cmd_remove(manager, sys.argv[2])

        elif command == "unsubscribe":
            if len(sys.argv) < 3:
                print("사용법: python scripts/manage_recipients.py unsubscribe <email>")
                sys.exit(1)
            cmd_unsubscribe(manager, sys.argv[2])

        elif command == "resubscribe":
            if len(sys.argv) < 3:
                print("사용법: python scripts/manage_recipients.py resubscribe <email>")
                sys.exit(1)
            cmd_resubscribe(manager, sys.argv[2])

        elif command == "init":
            cmd_init(manager)

        else:
            print(f"알 수 없는 명령어: {command}")
            print(__doc__)
            sys.exit(1)

    except Exception as e:
        print(f"오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
