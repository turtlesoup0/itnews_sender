# VPC 엔드포인트 설정 가이드

## 개요

Lambda 함수가 DynamoDB 및 SSM Parameter Store에 접근할 때 VPC 엔드포인트를 사용하면 다음과 같은 장점이 있습니다:

- **보안 강화**: 인터넷 게이트웨이 불필요, 프라이빗 네트워크 격리
- **비용 절감**: 데이터 전송 비용 없음 (Gateway 엔드포인트는 무료)
- **성능 향상**: AWS 백본 네트워크 사용

---

## 전제조건

Lambda 함수가 VPC 내에서 실행되어야 합니다. 현재 Lambda가 VPC 밖에서 실행 중이라면, VPC 설정이 먼저 필요합니다.

### 1단계: Lambda VPC 상태 확인

```bash
aws lambda get-function-configuration \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --query 'VpcConfig'
```

**출력 예시:**

```json
{
    "SubnetIds": [],
    "SecurityGroupIds": [],
    "VpcId": ""
}
```

- 빈 값이면 VPC 밖에서 실행 중 → **1-A. Lambda VPC 설정** 필요
- 값이 있으면 VPC 내에서 실행 중 → **2단계**로 이동

---

## 1-A. Lambda VPC 설정 (선택사항)

⚠️ **주의**: Lambda를 VPC 내에 배치하면 인터넷 접근이 차단됩니다. 전자신문 사이트 접근을 위해 NAT Gateway가 필요합니다.

### VPC 및 서브넷 선택

```bash
# 기본 VPC 확인
aws ec2 describe-vpcs --region ap-northeast-2 --filters "Name=is-default,Values=true"

# 프라이빗 서브넷 2개 선택 (Lambda는 최소 2개 필요)
aws ec2 describe-subnets --region ap-northeast-2 --filters "Name=vpc-id,Values=<VPC_ID>"
```

### Lambda 보안 그룹 생성

```bash
aws ec2 create-security-group \
  --group-name etnews-lambda-sg \
  --description "Security group for etnews-pdf-sender Lambda" \
  --vpc-id <VPC_ID> \
  --region ap-northeast-2

# 보안 그룹 ID 저장
SG_ID=<출력된_보안그룹_ID>
```

### Lambda에 VPC 설정 적용

```bash
aws lambda update-function-configuration \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --vpc-config SubnetIds=<서브넷1>,<서브넷2>,SecurityGroupIds=$SG_ID
```

---

## 2단계: DynamoDB VPC 엔드포인트 생성

DynamoDB는 **Gateway 엔드포인트**를 사용합니다 (무료).

### 라우팅 테이블 확인

```bash
# Lambda가 사용 중인 서브넷의 라우팅 테이블 확인
aws ec2 describe-route-tables \
  --region ap-northeast-2 \
  --filters "Name=association.subnet-id,Values=<서브넷_ID>"
```

### DynamoDB Gateway 엔드포인트 생성

```bash
aws ec2 create-vpc-endpoint \
  --vpc-id <VPC_ID> \
  --service-name com.amazonaws.ap-northeast-2.dynamodb \
  --route-table-ids <라우팅_테이블_ID1> <라우팅_테이블_ID2> \
  --region ap-northeast-2
```

**결과 확인:**
```bash
aws ec2 describe-vpc-endpoints \
  --region ap-northeast-2 \
  --filters "Name=service-name,Values=com.amazonaws.ap-northeast-2.dynamodb"
```

---

## 3단계: SSM Parameter Store VPC 엔드포인트 생성

SSM은 **Interface 엔드포인트**를 사용합니다 (시간당 $0.01).

### Interface 엔드포인트 생성

```bash
aws ec2 create-vpc-endpoint \
  --vpc-id <VPC_ID> \
  --vpc-endpoint-type Interface \
  --service-name com.amazonaws.ap-northeast-2.ssm \
  --subnet-ids <서브넷1> <서브넷2> \
  --security-group-ids $SG_ID \
  --private-dns-enabled \
  --region ap-northeast-2
```

**비용**: ~$0.01/시간 × 730시간 = **$7.30/월**

### 보안 그룹 인바운드 규칙 추가

Lambda → SSM 엔드포인트 통신 허용:

```bash
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 443 \
  --source-group $SG_ID \
  --region ap-northeast-2
```

---

## 4단계: NAT Gateway 설정 (인터넷 접근용)

Lambda가 전자신문 사이트에 접근하려면 NAT Gateway가 필요합니다.

### Elastic IP 할당

```bash
aws ec2 allocate-address --domain vpc --region ap-northeast-2
```

### NAT Gateway 생성

```bash
# 퍼블릭 서브넷에 NAT Gateway 생성
aws ec2 create-nat-gateway \
  --subnet-id <퍼블릭_서브넷_ID> \
  --allocation-id <Elastic_IP_할당_ID> \
  --region ap-northeast-2
```

**비용**: ~$0.045/시간 × 730시간 = **$32.85/월** + 데이터 전송 비용

### 프라이빗 라우팅 테이블에 NAT 경로 추가

```bash
aws ec2 create-route \
  --route-table-id <프라이빗_라우팅_테이블_ID> \
  --destination-cidr-block 0.0.0.0/0 \
  --nat-gateway-id <NAT_게이트웨이_ID> \
  --region ap-northeast-2
```

---

## 비용 요약

| 항목 | 비용 |
|------|------|
| **DynamoDB Gateway 엔드포인트** | $0 (무료) |
| **SSM Interface 엔드포인트** | $7.30/월 |
| **NAT Gateway** | $32.85/월 + 데이터 전송 |
| **합계** | **~$40/월** |

⚠️ **비용 주의**: NAT Gateway는 비싸므로 실제 필요성을 고려해야 합니다.

---

## 권장사항

### 최소 비용 구성 (DynamoDB만)

현재 Lambda가 VPC 밖에서 실행 중이라면:
- ✅ **VPC 설정 없이 현재 상태 유지**
- ✅ DynamoDB는 이미 프라이빗 엔드포인트로 접근 가능
- ✅ 추가 비용 없음

### 보안 강화 구성 (전체 VPC)

보안이 최우선이라면:
1. Lambda VPC 설정
2. DynamoDB Gateway 엔드포인트 (무료)
3. SSM Interface 엔드포인트 ($7.30/월)
4. NAT Gateway ($40/월)
   - 총 비용: **~$47/월**

---

## 테스트

VPC 엔드포인트 설정 후 Lambda 함수 테스트:

```bash
# TEST 모드 실행
aws lambda invoke \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --payload '{"mode":"test"}' \
  --cli-read-timeout 300 \
  response.json

# 로그 확인
aws logs tail /aws/lambda/etnews-pdf-sender --follow
```

**예상 결과**:
- DynamoDB 접근 정상
- SSM Parameter Store 접근 정상
- PDF 다운로드 정상 (NAT Gateway 필요)

---

## 롤백

문제 발생 시 VPC 설정 제거:

```bash
aws lambda update-function-configuration \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --vpc-config SubnetIds=[],SecurityGroupIds=[]
```

---

## 결론

**현재 권장 구성**: VPC 설정 없이 유지

- 비용: $0 추가
- 보안: 충분 (IAM 권한 + Parameter Store KMS 암호화)
- DynamoDB/SSM은 이미 AWS 프라이빗 네트워크 사용

**VPC 설정 고려 대상**:
- 규제 준수 요구사항
- 추가 네트워크 격리 필요
- 월 $40+ 추가 비용 감수 가능

---

**작성일**: 2026-01-28
**참고 문서**:
- [AWS Lambda VPC Networking](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html)
- [VPC Endpoints for DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/vpc-endpoints-dynamodb.html)
- [VPC Endpoints Pricing](https://aws.amazon.com/privatelink/pricing/)
