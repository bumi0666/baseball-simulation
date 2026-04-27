from scenes.base_scene import Scene
from ui.button import Button
from config import *
from ui.layout import get_common_buttons, draw_common_ui # 공통 레이아웃 임포트
import pygame, math

def attr_color(val):
    if val >= 80:
        return (60, 180, 75)    # 초록 (매우 좋음)
    elif val >= 70:
        return (240, 200, 80)   # 노랑 (좋음)
    elif val >= 60:
        return (230, 150, 60)   # 주황 (보통)
    else:
        return (200, 80, 80)    # 빨강 (낮음)

def draw_radar_chart(surface, player, cx, cy, radius=28):
    """
    오각형 레이더 차트를 그립니다.
    cx, cy: 차트 중심 좌표
    radius: 최대값(100) 기준 반지름
    """
    if player.is_pitcher():
        keys   = ["velocity", "control", "stamina", "stuff", "defense"]
        labels = ["VEL", "CON", "STA", "STF", "DEF"]
        color  = (100, 180, 255)   # 파란 계열
    else:
        keys   = ["contact", "power", "eye", "run", "defense"]
        labels = ["CTC", "POW", "EYE", "RUN", "DEF"]
        color  = (100, 255, 160)   # 초록 계열

    

    n = len(keys)
    # 각도: 위쪽(-90도)부터 시계방향
    angles = [math.radians(-90 + i * 360 / n) for i in range(n)]
    label_font = pygame.font.SysFont(None, 16)

    # 배경 오각형 (최대값 기준)
    bg_pts = [(cx + radius * math.cos(a), cy + radius * math.sin(a)) for a in angles]
    pygame.draw.polygon(surface, (50, 50, 60), bg_pts)
    pygame.draw.polygon(surface, (80, 80, 90), bg_pts, 1)

    label_inset = radius * 0.6
    for label, angle in zip(labels, angles):
        lx = cx + label_inset * math.cos(angle)
        ly = cy + label_inset * math.sin(angle)
        label_surf = label_font.render(label, True, (180, 180, 180))
        surface.blit(label_surf, (lx - label_surf.get_width() // 2, ly - label_surf.get_height() // 2))

   
    # 능력치 오각형
    vals = []
    for k in keys:
        if k in player.attr:
            vals.append(player.get_attr(k))
        else:
            vals.append(0)

    stat_pts = [
        (cx + (v / 100) * radius * math.cos(a),
         cy + (v / 100) * radius * math.sin(a))
        for v, a in zip(vals, angles)
    ]
    # 반투명 채우기
    stat_surf = pygame.Surface((radius * 2 + 10, radius * 2 + 10), pygame.SRCALPHA)
    offset = radius + 5
    local_pts = [(p[0] - cx + offset, p[1] - cy + offset) for p in stat_pts]
    pygame.draw.polygon(stat_surf, (*color, 80), local_pts)
    pygame.draw.polygon(stat_surf, (*color, 220), local_pts, 1)
    surface.blit(stat_surf, (cx - offset, cy - offset))

    # 꼭짓점 점
    for pt in stat_pts:
        pygame.draw.circle(surface, color, (int(pt[0]), int(pt[1])), 2)



    label_offset = radius + 1  # 꼭짓점에서 얼마나 더 바깥에 쓸지
    for i, (label, val, angle) in enumerate(zip(labels, vals, angles)):
        lx = cx + label_offset * math.cos(angle)
        ly = cy + label_offset * math.sin(angle)

        text = f"{val}"
        surf = label_font.render(text, True, color)

        # 각도에 따라 텍스트 정렬 (왼쪽/오른쪽/가운데)
        cos_a = math.cos(angle)
        if cos_a > 0.3:        # 오른쪽
            tx = lx
        elif cos_a < -0.3:     # 왼쪽
            tx = lx - surf.get_width()
        else:                  # 위/아래 중앙
            tx = lx - surf.get_width() // 2

        sin_a = math.sin(angle)
        if sin_a < -0.3:       # 위
            ty = ly - surf.get_height()
        else:                  # 아래 or 옆
            ty = ly - surf.get_height() // 2

        surface.blit(surf, (tx, ty))

class SquadScene(Scene):
    def __init__(self, players, state):
        self.players = players
        self.state = state
        
        self.dragging_player = None  # 현재 드래그 중인 선수 객체
        self.drag_offset = (0, 0)    # 마우스와 슬롯 중심 간의 거리
        
        # GameState에 이미 정의되어 있으므로 보장되지만, 없을 경우를 대비한 안전장치
        if not hasattr(self.state, 'lineup'):
            self.state.lineup = {k: None for k in ["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]}
        if not hasattr(self.state, 'batting_order'):
            self.state.batting_order = [None] * 9
            
        self.common_buttons = get_common_buttons(self)
        self.FONT = FONT
        self.SMALL_FONT = pygame.font.SysFont(None, 20)
        
        # UI 레이아웃을 위해 야구장 좌표를 중앙(x=700 부근)으로 이동
        self.positions = {
            "P":  (700, 420), "C":  (700, 600),
            "1B": (880, 380), "2B": (800, 250), "3B": (520, 380), "SS": (600, 250),
            "LF": (420+40, 170), "CF": (700, 100), "RF": (980-40, 170), "DH": (880, 550)
        }
        
        self.pos_buttons = []
        self.player_cards = []
        self.selected_pos = "P"
        self.scroll_y = 0
        
        self.selected_order_idx = None  # 현재 선택된 타순 번호 (0~8)
        # 타순 슬롯 클릭을 위한 버튼들
        self.order_buttons = []
        self.setup_order_buttons()
        
        self.setup_pos_buttons()
        self.filter_players("P")

    def setup_pos_buttons(self):
        self.pos_buttons = []
        for pos, (px, py) in self.positions.items():
            btn = Button((px - 35, py - 25, 70, 50), pos, lambda p=pos: self.filter_players(p))
            self.pos_buttons.append(btn)

    def filter_players(self, pos):
        self.selected_pos = pos
        self.scroll_y = 0

        active = [p for p in self.players if p.status.get("roster", "active") == "active"]
    
        if pos == "P":
        # 1. 투수 클릭 시: 투수만 표시
            self.filtered_players = [p for p in active if p.pos == "P"]
        
        elif pos == "DH":
        # 2. 지명타자 클릭 시: 투수를 제외한 모든 타자(야수) 표시
            self.filtered_players = [p for p in active if p.pos != "P"]
        
        else:
        # 3. 수비 포지션(C, 1B, SS 등) 클릭 시: 
        # 해당 위치가 주포지션인 선수만 표시 (또는 해당 포지션 타자들만)
            self.filtered_players = [p for p in active if p.pos == pos]
        
        # [참고] 만약 유격수(SS) 자리에 2루수(2B)도 세우고 싶다면?
        # 아래처럼 "투수가 아닌 모든 타자"를 보여주되, 포지션이 맞는 사람을 위로 올리는 정렬을 쓸 수도 있습니다.
        # self.filtered_players = sorted(
        #     [p for p in self.players if p.pos != "P"],
        #     key=lambda x: x.pos != pos  # 선택한 포지션과 일치하는 선수가 위로 옴
        # )

        self.setup_player_cards()
        
    def setup_player_cards(self):
        self.player_cards = []
        panel_x = 1030 # 우측 패널 위치 조정
        for i, p in enumerate(self.filtered_players):
            btn = Button((panel_x + 10, 0, 230, 65), "", lambda player=p: self.assign_to_lineup(player))
            self.player_cards.append((btn, p))
            
    def setup_order_buttons(self):
        self.order_buttons = []
        order_x, order_y = 220, 40
        for i in range(9):
            slot_y = order_y + 50 + (i * 65)
            # 타순 슬롯을 버튼으로 만듦 (클릭 시 해당 번호를 수정 모드로)
            btn = Button((order_x, slot_y, 175, 55), "", lambda idx=i: self.select_order_slot(idx))
            self.order_buttons.append(btn)

    def select_order_slot(self, idx):
        self.selected_order_idx = idx
        print(f"Editing Batting Order #{idx + 1}")

    def assign_to_lineup(self, player):
        # [모드 A] 타순 지정 모드
        if self.selected_order_idx is not None:
            # 투수인지 확인
            if player.pos == "P":
                print("FAIL: 투수는 타순에 포함될 수 없습니다. DH를 이용하세요!")
                return

            if player in self.state.lineup.values():
                # 이미 타순에 있다면 위치 교환을 위해 기존 위치 제거
                if player in self.state.batting_order:
                    old_idx = self.state.batting_order.index(player)
                    self.state.batting_order[old_idx] = None
            
                self.state.batting_order[self.selected_order_idx] = player
                self.selected_order_idx = None

        # [모드 B] 필드 배치 모드 (숫자 버튼 안 누름)
        else:
            # 1. 교체 전, 현재 해당 포지션에 있던 기존 선수 확인
            old_player = self.state.lineup.get(self.selected_pos)
            
            # 2. 기존 선수가 타순에 있었다면 그 선수만 제거 (전체 초기화 대신)
            if old_player and old_player in self.state.batting_order:
                idx = self.state.batting_order.index(old_player)
                self.state.batting_order[idx] = None
                print(f"DEBUG: {old_player.name}가 필드에서 나감에 따라 타순에서도 제외되었습니다.")

            # 3. 중복 포지션 제거 (새 선수가 이미 다른 포지션에 있었다면 그곳을 비움)
            for pos, p in self.state.lineup.items():
                if p == player: 
                    self.state.lineup[pos] = None
            
            # 4. 포지션 배정
            self.state.lineup[self.selected_pos] = player
            print(f"FIELD UPDATED: {self.selected_pos} -> {player.name}")
        
    def select_order_slot(self, idx):
        # 10개 슬롯(P + 야수8 + DH)이 모두 차 있는지 확인
        is_field_complete = all(p is not None for p in self.state.lineup.values())
    
        if is_field_complete:
            self.selected_order_idx = idx
        else:
            print("Notice: 투수와 지명타자(DH)를 포함한 10명을 모두 배치해야 합니다.")

    def draw(self, screen):
        screen.fill((20, 20, 20))
        draw_common_ui(screen, self.state, self.FONT)

        # --- 1. 좌측: 1~9번 타순 (Batting Order) ---
        order_x, order_y = 220, 40
        pygame.draw.rect(screen, (30, 35, 40), (order_x - 5, order_y - 5, 185, 650))
        screen.blit(self.FONT.render("LINEUP", True, (0, 255, 255)), (order_x + 10, order_y + 5))
        
        for i, btn in enumerate(self.order_buttons):
            slot_y = order_y + 50 + (i * 65)
            
            # 강조 표시
            is_selected = (self.selected_order_idx == i)
            btn.color = (80, 100, 150) if is_selected else (50, 50, 55)
            btn.draw(screen)
            
            p = self.state.batting_order[i]
            
            if p:
                # --- [추가] 이 선수가 필드의 어느 포지션인지 찾기 ---
                pos_label = ""
                for pos, player in self.state.lineup.items():
                    if player == p:
                        pos_label = pos
                        break
                
                # 포지션을 포함한 텍스트 (예: (1) [SS] 9. 김철수)
                order_txt = f"({i+1}) [{pos_label}] {p.backnumber}. {p.name}"
                clr = (255, 255, 255)
            else:
                order_txt = f"({i+1}) -------"
                clr = (100, 100, 100)
                
            screen.blit(self.SMALL_FONT.render(order_txt, True, clr), (order_x + 10, slot_y + 20))

        # --- 2. 중앙: 야구장 필드 (Field) ---
        line_points = [(700, 130), (950, 380), (700, 630), (450, 380)]
        pygame.draw.polygon(screen, (150, 100, 50), line_points, 3)

        for btn in self.pos_buttons:
            pos_key = btn.text
            btn.color = (100, 150, 255) if pos_key == self.selected_pos else (60, 60, 60)
            btn.draw(screen)
            
            starter = self.state.lineup.get(pos_key)
            name_str = starter.name if starter else "EMPTY"
            name_color = (200, 255, 200) if starter else (120, 120, 120)
            name_surf = self.SMALL_FONT.render(name_str, True, name_color)
            screen.blit(name_surf, (btn.rect.centerx - name_surf.get_width()//2, btn.rect.bottom + 5))

        # --- 3. 우측: 선수 리스트 (기존 코드 유지) ---
        panel_x = 1030
        pygame.draw.rect(screen, (35, 35, 40), (panel_x, 20, 250, 680))
        for i, (btn, p) in enumerate(self.player_cards):
            row_y = 60 + (i * 75) + self.scroll_y + 40
            
            if 50 < row_y < 670:
                btn.rect.y = row_y
                is_assigned = (
                    p in self.state.lineup.values() or 
                    p in self.state.batting_order or 
                    p in self.state.bullpen
                )
                if is_assigned:
                    btn.color = (40, 60, 100)  # 소속됨 표시 색상
                else:
                    btn.color = (60, 60, 65)
                btn.draw(screen)
                ovr = p.calculate_ovr()
                
                prefix = "[IN] " if is_assigned else ""
                name_text = f"{prefix}{p.backnumber}. {p.name} ({ovr})"
                name_color = (0, 255, 255) if is_assigned else (255, 255, 255)
                
                screen.blit(self.SMALL_FONT.render(name_text, True, name_color), (panel_x + 20, row_y + 8))
                cond = p.status.get("condition", 50)
                cond_color = (0, 255, 0) if cond > 70 else (255, 255, 0) if cond > 40 else (255, 0, 0)
                pygame.draw.circle(screen, cond_color, (panel_x + 25, row_y + 35), 5)
                health = p.status.get("health", 1000)
                pygame.draw.rect(screen, (80, 80, 80), (panel_x + 40, row_y + 32, 80, 8))
                pygame.draw.rect(screen, attr_color(health), (panel_x + 40, row_y + 32, 80 * (min(1000, health)/1000), 8))
                draw_radar_chart(screen, p, cx=panel_x + 200, cy=row_y + 36, radius=28)

        for btn in self.common_buttons:
            btn.draw(screen)
            
        if self.dragging_player:
            m_pos = pygame.mouse.get_pos()
            # 마우스를 따라다니는 반투명한 박스
            drag_surf = pygame.Surface((120, 40), pygame.SRCALPHA)
            pygame.draw.rect(drag_surf, (0, 200, 255, 180), (0, 0, 120, 40), border_radius=10)
            
            text_surf = self.SMALL_FONT.render(self.dragging_player.name, True, (255, 255, 255))
            drag_surf.blit(text_surf, (60 - text_surf.get_width()//2, 20 - text_surf.get_height()//2))
            
            screen.blit(drag_surf, (m_pos[0] - 60, m_pos[1] - 20))

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        all_btns = self.common_buttons + self.pos_buttons + [c[0] for c in self.player_cards] + self.order_buttons
        
        for btn in all_btns:
            btn.update_hover(mouse_pos)

        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN:
                if e.button == 1: # 좌클릭
                    # 1. 일단 어떤 버튼이든 클릭 이벤트는 먼저 처리 (필드 선수 교체 등)
                    clicked_btn = None
                    for btn in all_btns:
                        if btn.rect.collidepoint(mouse_pos):
                            clicked_btn = btn
                            res = btn.handle_event(e)
                            if res: return res
                            break
                    
                    # 2. [추가] 클릭한 버튼이 필드 포지션 버튼이고, 9명이 다 찼다면 드래그 준비
                    # 일반 클릭과 드래그 시작을 동시에 허용합니다.
                    is_field_complete = all(p is not None for p in self.state.lineup.values())
                    if is_field_complete and clicked_btn in self.pos_buttons:
                        self.dragging_player = self.state.lineup.get(clicked_btn.text)

                elif e.button == 3: # 우클릭 해제
                    for btn in self.pos_buttons:
                        if btn.rect.collidepoint(mouse_pos):
                            p = self.state.lineup.get(btn.text)
                            # 타순에서 이 선수만 찾아서 제거
                            if p and p in self.state.batting_order:
                                idx = self.state.batting_order.index(p)
                                self.state.batting_order[idx] = None
                            
                            # 필드에서 제거
                            self.state.lineup[btn.text] = None
                            print(f"Released {btn.text} and removed from lineup.")

            elif e.type == pygame.MOUSEBUTTONUP:
                if e.button == 1:
                    if self.dragging_player:
                        if self.dragging_player.pos == "P":
                            self.dragging_player = None
                            return
                        # 타순 슬롯 위에 놓았는지 확인
                        for i, btn in enumerate(self.order_buttons):
                            if btn.rect.collidepoint(mouse_pos):
                                if self.dragging_player in self.state.batting_order:
                                    old_idx = self.state.batting_order.index(self.dragging_player)
                                    self.state.batting_order[old_idx] = None
                                self.state.batting_order[i] = self.dragging_player
                                break
                        self.dragging_player = None 

            elif e.type == pygame.MOUSEWHEEL:
                # 상단 제한: 0보다 커질 수 없음
                if e.y > 0: 
                    self.scroll_y = min(0, self.scroll_y + 50)
                # 하단 제한: 리스트의 끝까지만 내려감
                else:
                    # 카드 1개당 높이(75) * 카드 개수 = 전체 높이
                    total_height = len(self.player_cards) * 75
                    # 표시되는 패널의 높이 (약 600px 정도로 잡음)
                    visible_height = 580 
            
                    # 리스트가 화면보다 길 때만 하단 제한 계산
                    if total_height > visible_height:
                        max_scroll = -(total_height - visible_height)
                        self.scroll_y = max(max_scroll, self.scroll_y - 50)
                
        return None

    
    