from turtle import color

import pygame
from datetime import date, timedelta
from ui.button import Button
from config import *

def get_common_buttons(scene_obj):
    """모든 scene에서 공통으로 사용하는 사이드바 버튼 리스트 반환"""

    scene_key_map = {
        "HubScene": "hub",
        "InboxScene": "inbox",
        "TeamScene": "team",
        "SquadScene": "squad",
        "StaffScene": "staff",
        "TrainingScene": "train",
        "MedicalScene": "medical",
        "ScheduleScene": "schedule",
        "TransferScene": "transfer",
        "FinanceScene": "finance",
        "TeamDetailScene": "info",
        "ReserveScene": "reserve",
    }

    active_key = getattr(scene_obj, "nav_key", None)
    if active_key is None:
        active_key = scene_key_map.get(scene_obj.__class__.__name__)

    add = 30
    btn_x = 20
    btn_w = 150
    btn_h = 40

    nav_items = [
        ("Home", "hub", 60 + add),
        ("Inbox", "inbox", 110 + add),
        ("Player", "team", 160 + add),
        ("Squad", "squad", 210 + add),
        ("Staff", "staff", 260 + add),
        ("Training", "train", 310 + add),
        ("Medical", "medical", 360 + add),
        ("Schedule", "schedule", 410 + add),
        ("Transfers", "transfer", 460 + add),
        ("Finances", "finance", 510 + add),
        ("Team", "info", 560 + add),
        ("Reserve", "reserve", 610 + add),
    ]

    buttons = []

    for label, target, y in nav_items:
        btn = Button(
            (btn_x, y, btn_w, btn_h),
            label,
            lambda t=target: t
        )
        btn.active = (target == active_key)
        buttons.append(btn)

    next_btn = Button(
        (width - 190, 20, 160, 40),
        "NEXT",
        lambda: "advance_time"
    )
    next_btn.active = False
    buttons.append(next_btn)

    return buttons

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

    def draw(self, screen):
        is_active = getattr(self, "active", False)

        if is_active:
            color = (45, 80, 135)
            border_color = (90, 180, 255)
        elif self.hover:
            color = (35, 35, 35)
            border_color = (90, 90, 90)
        else:
            color = (0, 0, 0)
            border_color = (40, 40, 40)

        pygame.draw.rect(screen, color, self.rect)
        pygame.draw.rect(screen, border_color, self.rect, 2)

        if is_active:
            pygame.draw.rect(
                screen,
                (0, 200, 255),
                (self.rect.x, self.rect.y, 5, self.rect.height)
            )

        text_surf = self.font.render(self.text, True, white)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)