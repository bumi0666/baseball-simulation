import pygame
from datetime import date, timedelta
from ui.button import Button
from config import *

def get_common_buttons(scene_obj):
    """모든 씬에서 공통으로 사용할 버튼 리스트 반환"""
    gap = 70
    add = 30
    
    # 사이드바 버튼들의 X 좌표와 너비 통일
    btn_x = 20
    btn_w = 150
    btn_h = 40
    
    return [
        Button((btn_x, 60+add, btn_w, btn_h), "Home", lambda: "hub"),
        Button((btn_x, 110+add, btn_w, btn_h), "Inbox", lambda: "inbox"),
        Button((btn_x, 160+add, btn_w, btn_h), "Player", lambda: "team"),
        Button((btn_x, 210+add, btn_w, btn_h), "Squad", lambda: "squad"),
        Button((btn_x, 260+add, btn_w, btn_h), "Staff", lambda: "staff"),
        Button((btn_x, 310+add, btn_w, btn_h), "Training", lambda: "train"),
        Button((btn_x, 360+add, btn_w, btn_h), "Medical", lambda: "medical"),
        Button((btn_x, 410+add, btn_w, btn_h), "Schedule", lambda: "schedule"),
        Button((btn_x, 460+add, btn_w, btn_h), "Transfers", lambda: "transfer"),
        Button((btn_x, 510+add, btn_w, btn_h), "Finances", lambda: "finance"),
        Button((btn_x, 560+add, btn_w, btn_h), "Team", lambda: "info"),
        Button((btn_x, 610+add, btn_w, btn_h), "Reserve", lambda: "reserve"),
        
        # 우측 상단 진행 버튼 (Next)
        Button((width - 190, 20, 160, 40), "NEXT", lambda: "advance_time")
    ]

def draw_common_ui(screen, state, font):
    """사이드바 배경과 날짜 표시 (GameState 객체 대응)"""
    
    # 1. 사이드바 배경 (너비 190px 고정)
    pygame.draw.rect(screen, (220, 220, 220), (0, 0, 190, height))
    pygame.draw.rect(screen, (180, 180, 180), (188, 0, 2, height)) # 경계선 추가로 입체감 부여
    
    # 2. 날짜 계산 및 출력 (객체 문법 . 사용)
    base_y, base_m, base_d = state.base_date
    start_date = date(base_y, base_m, base_d)
    current_date = start_date + timedelta(days=state.current_day - 1)
    
    date_str = current_date.strftime("%Y-%m-%d")
    day_str = f"Day {state.current_day}"
    
    # 텍스트 출력 (사이드바 안쪽 상단)
    date_surf = font.render(date_str, True, (40, 40, 40))
    day_surf = font.render(day_str, True, (100, 100, 100))
    
    screen.blit(date_surf, (20, 20))
    screen.blit(day_surf, (20, 20 + font.get_height()))
    
    unread_count = sum(1 for msg in state.inbox if not msg.get("read", False))
    
    if unread_count > 0:
        # get_common_buttons의 좌표값 참조: btn_x=20, 120+add(30)=150, btn_w=150
        # Inbox 버튼의 우측 상단 모서리 좌표 계산
        badge_x = 20 + 150 - 5 + 10  # btn_x + btn_w - 마진
        badge_y = 150 + 5       # 120 + add + 마진
        
        # 빨간 원 그리기
        pygame.draw.circle(screen, (220, 20, 20), (badge_x, badge_y), 10)
        
        # 숫자 출력용 작은 폰트 (없으면 기본 폰트 사용)
        try:
            small_font = pygame.font.SysFont("malgungothic", 12, bold=True)
        except:
            small_font = pygame.font.SysFont(None, 18)
            
        count_surf = small_font.render(str(unread_count), True, (255, 255, 255))
        count_rect = count_surf.get_rect(center=(badge_x, badge_y))
        screen.blit(count_surf, count_rect)