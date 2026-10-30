from scenes.base_scene import Scene
from ui.button import Button
from config import *
from saveload import list_save_slots, delete_slot
import pygame, sys

pygame.mixer.init()

class TitleScene(Scene):
    ROWS = 3                       # 한 번에 보이는 저장 슬롯 수 (나머지는 휠/▲▼로 스크롤)

    def __init__(self):
        self.bg = pygame.image.load(resource_path("assets/main.png"))
        self.bg = pygame.transform.scale(self.bg, (1280, 720))
        self.slot_font = pygame.font.SysFont(None, 26)
        self.slots = list_save_slots()
        self.scroll = 0
        self.confirm = None        # 삭제 확인 중인 슬롯 번호 (같은 삭제 버튼을 한 번 더 눌러야 지워진다)
        self.fixed = [
            Button((520, 240, 240, 56), "New Game", self.new_game),
            Button((520, 510, 240, 50), "Option", self.option),
            Button((520, 570, 240, 50), "Quit", self.quit),
        ]
        self.buttons = []
        self._rebuild()

    def refresh_slots(self):
        self.slots = list_save_slots()
        self.scroll = min(self.scroll, max(0, len(self.slots) - self.ROWS))
        self.confirm = None
        self._rebuild()

    def _rebuild(self):
        """보이는 슬롯 줄(불러오기 버튼 + 삭제 버튼)과 스크롤 버튼을 다시 만든다."""
        self.buttons = list(self.fixed)
        for k, info in enumerate(self.slots[self.scroll:self.scroll + self.ROWS]):
            y = 316 + k * 64
            n = info["slot"]
            self.buttons.append(Button((440, y, 320, 54), self.slot_label(info), lambda n=n: self.load_slot(n), font=self.slot_font))
            self.buttons.append(Button((770, y, 70, 54), "Sure?" if self.confirm == n else "Delete",
                                       lambda n=n: self.delete(n), font=self.slot_font, active=self.confirm == n))
        if len(self.slots) > self.ROWS:
            self.buttons.append(Button((850, 316, 44, 54), "^", lambda: self.scroll_by(-1)))
            self.buttons.append(Button((850, 442, 44, 54), "v", lambda: self.scroll_by(1)))

    def scroll_by(self, d):
        new = max(0, min(max(0, len(self.slots) - self.ROWS), self.scroll + d))
        if new != self.scroll:
            self.scroll = new
            self.confirm = None
            self._rebuild()
        return None

    def slot_label(self, info):
        text = "Slot %d  %s  %s" % (info["slot"], info.get("user_team", ""), info.get("game_date") or "Day %s" % info.get("current_day", 1))
        size = info.get("size_mb")
        return text + ("  %.0fMB" % size if size else "")

    def delete(self, slot):
        if self.confirm != slot:
            self.confirm = slot
            self._rebuild()
            return None
        delete_slot(slot)
        self.refresh_slots()
        return None

    def update(self, events):
        for e in events:
            if e.type == pygame.MOUSEWHEEL:
                self.scroll_by(-e.y)
        return super().update(events)

    def new_game(self):
        return "hub"

    def load_slot(self, slot):
        if not any(s.get("slot") == slot for s in self.slots):
            return None
        return ("load_slot", slot)

    def option(self):
        return "option"
    
    def how(self):
        return "how"

    def quit(self):
        pygame.quit()
        sys.exit()

    def draw(self, screen):
        #screen.fill(black)
        screen.blit(self.bg, (0, 0))
        for btn in self.buttons:
            btn.draw(screen)
