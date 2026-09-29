# Time Black Market

> 오늘 편했던 만큼, 미래의 나는 바빠진다.

## 프로젝트 소개

**Time Black Market(시간 암시장)**은 오늘 처리하지 못해 미래로 이월된 업무의 예상 소요 시간을 `시간 부채(Time Debt)`로 계산하고, AI가 시간 부채의 변화와 상환 계획을 분석해주는 개인 AI 비서 서비스입니다.

사용자는 자신이 미래로 넘긴 업무와 예상 소요 시간을 기록하고, AI를 통해 현재 시간 부채, 최근 변화 추세, 상환 데드라인 및 적절한 상환 시점을 확인할 수 있습니다.

## 핵심 기능

- Current Time Debt
- 시간 부채 데이터 CRUD
- 신규 시간 차입 및 상환 기록
- 월별 Debt Calendar
- Repayment Deadline
- Repayment Recommendation Day
- 데이터 기반 AI 채팅
- 대화 기록 저장 및 불러오기
- 시간 부채 시계열 그래프
- CSV 데이터 내보내기
- Dark Mode
- GPT Function Calling
- MCP 연동

## 주요 개념

### Time Debt

오늘 완료하지 못해 미래로 이월된 업무의 예상 소요시간을 의미합니다.

### Borrowing

미래의 시간으로 업무를 넘기면서 새로운 시간 부채가 발생하는 것을 의미합니다.

### Repayment

기존에 이월했던 업무를 완료하여 시간 부채를 줄이는 것을 의미합니다.

### Repayment Deadline

업무의 실제 마감 시간과 예상 소요시간을 고려하여 계산한 최소 작업 시작 시점을 의미합니다.

### Repayment Recommendation Day

예정된 작업량과 사용 가능한 시간을 분석하여 기존 시간 부채를 상환하기 적합한 날짜를 추천합니다.

## 기술 스택

### Backend

- Python
- FastAPI
- Pydantic
- Firebase Admin SDK
- OpenAI API

### Frontend

- HTML
- CSS
- JavaScript

### Database

- Firebase Firestore

### Deployment

- Backend: Render
- Frontend: Vercel

## Project Status

🚧 In Development