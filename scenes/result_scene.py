from scenes.base_scene import Scene
from ui.button import Button
from config import *
import pygame, random

class ResultScene(Scene):
    def __init__(self, result, state):
        self.result = result
        self.state = state
        self.FONT = pygame.font.SysFont("malgungothic", 28)
        self.smallFONT = pygame.font.SysFont("malgungothic", 22)
        
        self.view_mode = "MY"
        self.toggle_btn = Button((1000, 30, 150, 40), "View: MY", self.toggle_view)
        
    def toggle_view(self):
        if self.view_mode == "MY":
            self.view_mode = "OPP"
            self.toggle_btn.text = "View: OPP"
        else:
            self.view_mode = "MY"
            self.toggle_btn.text = "View: MY"

    def outs_to_ip(self, outs):
        return f"{outs//3}.{outs%3}"

    def draw_header(self, screen):
        txt = f"{self.state.user_team} {self.result['my_score']} : {self.result['opp_score']} {self.result['opponent']}  ({self.result['result']})"
        screen.blit(self.FONT.render(txt, True, white), (50, 30))

    def draw_batters(self, screen, players, x, y):
        headers = ["AB", "H", "HR", "RBI", "BB", "SO", "SB"]
        screen.blit(self.smallFONT.render("Name", True, white), (x, y))
        for i, h in enumerate(headers):
            screen.blit(self.smallFONT.render(h, True, white), (x + 160+ i*80, y))

        y += 30
        pygame.draw.line(screen, white, (x, y), (x + 80*len(headers) + 160, y), 2)
        y += 10

        for p in players:
            if not p or p.pos == "P":
                continue
            #print(p.name)

            g = p.game_stats
            first = 0
            row = [
                g["ab"], g["h"], g["hr"],
                g["rbi"], g["bb"], g["so"], g["sb"]
            ]
            screen.blit(self.smallFONT.render(p.name, True, white),(x, y))

            for i, val in enumerate(row):
                screen.blit(self.smallFONT.render(str(val), True, white),
                            (x + 160 + i*80, y))
            y += 26

    def draw_pitchers(self, screen, players, x, y):
        headers = ["IP", "H", "R", "ER", "BB", "SO"]
        screen.blit(self.smallFONT.render("Name", True, white), (x, y))
        for i, h in enumerate(headers):
            screen.blit(self.smallFONT.render(h, True, white), (x + 160 + i*80, y))

        y += 30
        pygame.draw.line(screen, white, (x, y), (x + 80*len(headers) + 160, y), 2)
        y += 10

        for p in players:
            if not p or p.pos != "P" or p.game_stats["ip_outs"] == 0:
                continue
            #print(p.name)
            g = p.game_stats
            row = [
                self.outs_to_ip(g["ip_outs"]),
                g["h_allowed"],
                g["r_allowed"],
                g["er"],
                g["bb_p"],
                g["so_p"]
            ]
            screen.blit(self.smallFONT.render(p.name, True, white),(x, y))

            for i, val in enumerate(row):
                screen.blit(self.smallFONT.render(str(val), True, white),
                            (x + 160 + i*80, y))
            y += 26

    def draw(self, screen):
        screen.fill((20, 20, 20))
        screen.blit(self.FONT.render("Press Space to continue", True, (255, 255, 255)), (560, 640))
        self.draw_header(screen)
        if self.view_mode == "MY":
            players = self.result["my_players"]
        else:
            players = self.result["opp_players"]

        # 타자 테이블
        self.draw_batters(screen, players, 50, 100)

        # 투수 테이블 (아래쪽)
        self.draw_pitchers(screen, players, 50, 380)
        self.toggle_btn.draw(screen)

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        self.toggle_btn.update_hover(mouse_pos)

        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN:
                self.toggle_btn.handle_event(e)

            if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
                return "hub"

        return None

