"""AI 구단 피로 상수(baseball.py와 ai_lineup/ai_match가 함께 쓴다)"""
AI_REST_FATIGUE = 200        # AI 감독은 피로가 이 값을 넘은 주전을 쉬게 한다 (넘어서도 뛰면 부상 위험)
AI_HITTER_FATIGUE = 58       # 야수 1경기 피로 증가(포수는 1.6배). 하루에 process_day가 여러 번 불려 회복도 여러 번이라, 시즌 평균 부상 비율이 6~7%가 되게 맞춘 값
AI_PITCHER_FATIGUE = 80      # 선발 투수 1경기(100/체력 보정) 피로 증가
