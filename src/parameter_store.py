"""
AWS Systems Manager Parameter Store를 사용한 안전한 credential 관리
완전 무료이면서도 KMS 암호화 지원
"""
import json
import logging
import os
import boto3
from botocore.exceptions import ClientError
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ParameterStore:
    """AWS Systems Manager Parameter Store 클라이언트"""

    def __init__(self, region_name: str = "ap-northeast-2"):
        """
        Args:
            region_name: AWS 리전
        """
        self.region_name = region_name
        self.client = None
        self._cache: Optional[Dict[str, str]] = None

    def _get_client(self):
        """SSM 클라이언트 가져오기 (lazy loading)"""
        if self.client is None:
            self.client = boto3.client(
                service_name='ssm',
                region_name=self.region_name
            )
        return self.client

    def get_parameter(self, parameter_name: str) -> Dict[str, str]:
        """
        Parameter Store에서 파라미터 가져오기

        Args:
            parameter_name: 파라미터 이름 (예: /etnews/credentials)

        Returns:
            파라미터 딕셔너리

        Raises:
            Exception: 파라미터를 가져오는데 실패한 경우
        """
        # 캐시된 파라미터가 있으면 반환
        if self._cache is not None:
            logger.debug(f"캐시된 파라미터 사용: {parameter_name}")
            return self._cache

        try:
            logger.info(f"Parameter Store에서 파라미터 가져오기: {parameter_name}")
            client = self._get_client()

            response = client.get_parameter(
                Name=parameter_name,
                WithDecryption=True  # SecureString 복호화
            )

            # 파라미터 파싱
            parameter_value = response['Parameter']['Value']
            parameter_dict = json.loads(parameter_value)

            self._cache = parameter_dict
            logger.info(f"파라미터 로드 완료: {len(parameter_dict)} 항목")
            return parameter_dict

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Parameter Store 오류 ({error_code}): {e}")

            if error_code == 'ParameterNotFound':
                raise Exception(f"파라미터를 찾을 수 없습니다: {parameter_name}")
            elif error_code == 'AccessDeniedException':
                raise Exception(f"파라미터 접근 권한이 없습니다: {parameter_name}")
            else:
                raise

        except json.JSONDecodeError as e:
            logger.error(f"파라미터 JSON 파싱 실패: {e}")
            raise Exception("파라미터 값이 올바른 JSON 형식이 아닙니다")

        except Exception as e:
            logger.error(f"파라미터 로드 중 예상치 못한 오류: {e}")
            raise


# 전역 인스턴스
_parameter_store = ParameterStore()


def get_parameter(parameter_name: str, with_decryption: bool = True) -> str:
    """
    단일 Parameter 가져오기

    Args:
        parameter_name: Parameter 이름 (예: /etnews/admin-email)
        with_decryption: SecureString 복호화 여부

    Returns:
        Parameter 값 (문자열)
    """
    try:
        client = _parameter_store._get_client()
        response = client.get_parameter(
            Name=parameter_name,
            WithDecryption=with_decryption
        )
        return response['Parameter']['Value']
    except ClientError as e:
        logger.error(f"Parameter 조회 실패 ({parameter_name}): {e}")
        raise


def get_credentials(parameter_name: str = "/etnews/credentials") -> Dict[str, str]:
    """
    Credentials 가져오기

    Lambda 환경에서는 Parameter Store 사용,
    로컬 환경에서는 환경변수 사용

    Args:
        parameter_name: Parameter Store 파라미터 이름

    Returns:
        credentials 딕셔너리
    """
    # Lambda 환경 감지
    is_lambda = os.environ.get('AWS_EXECUTION_ENV') is not None

    if is_lambda:
        logger.info("Lambda 환경: Parameter Store 사용")
        return _parameter_store.get_parameter(parameter_name)
    else:
        logger.info("로컬 환경: 환경변수 사용")
        return {
            'ETNEWS_USER_ID': os.environ.get('ETNEWS_USER_ID', ''),
            'ETNEWS_PASSWORD': os.environ.get('ETNEWS_PASSWORD', ''),
            'GMAIL_USER': os.environ.get('GMAIL_USER', ''),
            'GMAIL_APP_PASSWORD': os.environ.get('GMAIL_APP_PASSWORD', ''),
            'RECIPIENT_EMAIL': os.environ.get('RECIPIENT_EMAIL', ''),
            'ICLOUD_EMAIL': os.environ.get('ICLOUD_EMAIL', ''),
            'ICLOUD_PASSWORD': os.environ.get('ICLOUD_PASSWORD', ''),
            'ICLOUD_FOLDER_NAME': os.environ.get('ICLOUD_FOLDER_NAME', 'IT뉴스'),
        }


if __name__ == "__main__":
    # 테스트
    try:
        credentials = get_credentials()
        print(f"Credentials 로드 완료: {len(credentials)} 항목")
        print(f"키 목록: {list(credentials.keys())}")
    except Exception as e:
        print(f"오류 발생: {e}")
