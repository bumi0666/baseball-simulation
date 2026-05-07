
from models import staff
from scenes.base_scene import Scene
from models.staff import Staff
from ui.button import Button
from config import *
from ui.layout import get_common_buttons, draw_common_ui 
import pygame

class StaffScene(Scene):
    def __init__(self, state):
        self.state = state
        self.FONT = pygame.font.SysFont("malgungothic", 25)
        self.SMALL_FONT = pygame.font.SysFont("malgungothic", 18)
        
        # 1. 스태프 보직 슬롯 정의
        self.roles = ["HD", "HC", "PC", "DC", "SC", "DR"]
        self.slot_buttons = []
        self.setup_slots()
        
        # 2. 보유 스태프 데이터 (없을 경우 초기화)
        if not hasattr(self.state, "owned_staff"):
            self.state.owned_staff = []

        if not hasattr(self.state, "staff_slots"):
            self.state.staff_slots = {}
        
        # 3. 공통 버튼 (뒤로가기 등)
        self.common_buttons = get_common_buttons(self)
        
        self.selected_role = "HD"
        self.staff_cards = []
        self.detail_buttons = []
        self.setup_staff_cards()

    def setup_slots(self):
        start_x = 300
        start_y = 90
        btn_w = 180
        btn_h = 70
        gap_x = 195
        gap_y = 85

        for i, role in enumerate(self.roles):
            col = i % 2
            row = i // 2
            x = start_x + col * gap_x
            y = start_y + row * gap_y

            btn = Button((x, y, btn_w, btn_h), role, lambda r=role: self.select_role(r))
            self.slot_buttons.append(btn)

    def select_role(self, role):
        self.selected_role = role
        self.setup_staff_cards()

    def setup_staff_cards(self):
        self.staff_cards = []
        self.detail_buttons = []

        start_x, start_y = 500, 350
        card_w = 750
        card_h = 72
        gap = 82

        role_staff = [
            s for s in self.state.owned_staff
            if s.role == self.selected_role
        ]

        for i, staff in enumerate(role_staff):
            btn = Button(
                (start_x, start_y + i * gap, card_w, card_h),
                "",
                lambda staff=staff: self.assign_staff(staff)
            )
            self.staff_cards.append((btn, staff))

            detail_btn = Button(
                (start_x + card_w - 105, start_y + i * gap + 40, 86, 24),
                "DETAIL",
                lambda staff=staff: ("staff_detail", staff),
                self.SMALL_FONT
            )
            self.detail_buttons.append(detail_btn)


    def assign_staff(self, staff):
        """스태프를 슬롯에 배정"""
        # 보직 일치 여부 확인
        if staff.role == self.selected_role:
            self.state.staff_slots[self.selected_role] = staff
            print(f"{staff.name} 배정 완료!")
        else:
            print(f"보직 불일치: {staff.name}은 {staff.role} 전용입니다.")

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        
        # 모든 버튼 업데이트 (슬롯 + 스태프 카드 + 공통 버튼)
        all_btns = self.slot_buttons + [c[0] for c in self.staff_cards] + self.detail_buttons + self.common_buttons
        for btn in all_btns:
            btn.update_hover(mouse_pos)

        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN:
                if e.button == 1:
                    for btn in self.detail_buttons + self.slot_buttons + [c[0] for c in self.staff_cards] + self.common_buttons:
                        res = btn.handle_event(e)
                        if res: return res
        return None

    def draw(self, screen):
        screen.fill((20, 20, 20))
        
        # 1. 공통 UI 먼저 그리기 (바닥에 깔림)
        draw_common_ui(screen, self.state, FONT)
        
        # 2. 우측 배경 판넬 좌표 수정
        # 버튼 시작이 130이므로 배경은 120부터 시작하도록 Y축 수정
        panel_rect = pygame.Rect(290, 60, 970, 640)
        pygame.draw.rect(screen, (45, 45, 50), panel_rect, border_radius=10)
        
        # --- 좌측: 보직 슬롯 (수정된 좌표로 그려짐) ---
        for btn in self.slot_buttons:
            is_active = (btn.text == self.selected_role)
            if is_active:
                btn.color = (0, 180, 255)  # 활성화된 색상
                # 선택 강조 외곽선 (사각형을 버튼보다 살짝 크게)
                pygame.draw.rect(screen, (255, 255, 255), btn.rect.inflate(6, 6), 2, border_radius=5)
            else:
                btn.color = (60, 60, 65)  # 비활성 색상
            btn.draw(screen)
            
            assigned = self.state.staff_slots.get(btn.text)
            if assigned:
                name_txt = self.SMALL_FONT.render(assigned.name, True, (255, 255, 255))
                star_txt = self.SMALL_FONT.render(assigned.get_star_text(), True, (255, 215, 0))
                screen.blit(name_txt, (btn.rect.x + 10, btn.rect.y + 40))
                screen.blit(star_txt, (btn.rect.x + 10, btn.rect.y + 65))

        # --- 우측: 보유 스태프 카드 리스트 ---
        for btn, staff in self.staff_cards:
            btn.draw(screen)

            title = getattr(staff, "title", "")
            salary = staff.salary() if hasattr(staff, "salary") else 0

            name_surf = self.FONT.render(
                f"[{staff.role}] {staff.name} - {title}",
                True,
                (255, 255, 255)
            )
            star_surf = self.FONT.render(
                staff.get_star_text(),
                True,
                (255, 215, 0)
            )
            desc_surf = self.SMALL_FONT.render(
                staff.effect_desc,
                True,
                (180, 180, 180)
            )
            salary_surf = self.SMALL_FONT.render(
                f"Salary: ${salary:,}",
                True,
                (180, 220, 180)
            )

            screen.blit(name_surf, (btn.rect.x + 20, btn.rect.y + 8))
            screen.blit(star_surf, (btn.rect.x + 20, btn.rect.y + 38))
            screen.blit(desc_surf, (btn.rect.x + 180, btn.rect.y + 40))
            screen.blit(salary_surf, (btn.rect.x + 560, btn.rect.y + 14))

        for btn in self.detail_buttons:
            btn.draw(screen)

        # 3. 공통 버튼(뒤로가기 등)은 가장 마지막에 그려서 클릭 우선순위 확보
        for btn in self.common_buttons:
            btn.draw(screen)
            
    def back(self):
        return "hub"
