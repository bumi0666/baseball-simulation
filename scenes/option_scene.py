from scenes.base_scene import Scene
from ui.button import Button
from config import *
import pygame
from ui.slider import Slider


class OptionScene(Scene):
    def __init__(self, state=None):
        self.state = state
        self.selected_slot = getattr(state, "active_save_slot", 1) if state is not None else 1
        self.bgm_slider = Slider((410, 395), 200, settings["vol_bgm"])
        self.sfx_slider = Slider((410, 455), 200, settings["vol_sfx"])

        self.buttons = [
            Button((450, 200, 120, 40), "CHANGE", self.toggle_difficulty),
            Button((450, 260, 120, 40), "CHANGE", self.toggle_fps),
            Button((450, 320, 120, 40), "CHANGE", self.toggle_language),
            Button((410, 505, 70, 42), "SLOT 1", lambda: self.select_slot(1), active=self.selected_slot == 1),
            Button((495, 505, 70, 42), "SLOT 2", lambda: self.select_slot(2), active=self.selected_slot == 2),
            Button((580, 505, 70, 42), "SLOT 3", lambda: self.select_slot(3), active=self.selected_slot == 3),
            Button((680, 505, 120, 42), "SAVE", self.save),
            Button((820, 505, 100, 42), "BACK", self.back),
        ]

    def select_slot(self, slot):
        self.selected_slot = slot
        if self.state is not None:
            self.state.active_save_slot = slot
        for btn in self.buttons:
            if btn.text.startswith("SLOT "):
                btn.active = btn.text == f"SLOT {slot}"
        return None

    def toggle_difficulty(self):
        curr = settings["difficulty"]
        idx = (DIFFICULTIES.index(curr) + 1) % len(DIFFICULTIES)
        settings["difficulty"] = DIFFICULTIES[idx]

    def toggle_fps(self):
        curr = settings["fps"]
        idx = (FPS_OPTIONS.index(curr) + 1) % len(FPS_OPTIONS)
        settings["fps"] = FPS_OPTIONS[idx]

    def toggle_language(self):
        curr = settings["language"]
        idx = (LANGUAGES.index(curr) + 1) % len(LANGUAGES)
        settings["language"] = LANGUAGES[idx]

    def back(self):
        if self.state is not None:
            return getattr(self.state, "prevscene", "title") or "title"
        return "title"

    def save(self):
        return ("save_game", self.selected_slot)

    def draw(self, screen):
        screen.fill((220, 220, 220))

        title = FONT.render("OPTIONS", True, black)
        screen.blit(title, (width // 2 - 50, 50))

        options_to_show = [
            (f"Difficulty: {settings['difficulty']}", 200),
            (f"FPS: {settings['fps']}", 260),
            (f"Language: {settings['language']}", 320),
            (f"BGM Volume: {int(settings['vol_bgm'] * 100)}%", 380),
            (f"SFX Volume: {int(settings['vol_sfx'] * 100)}%", 440),
            (f"Save Slot: {self.selected_slot}", 500),
        ]

        for text, y in options_to_show:
            txt_surf = FONT.render(text, True, (50, 50, 50))
            screen.blit(txt_surf, (150, y + 5))

        self.bgm_slider.draw(screen)
        self.sfx_slider.draw(screen)

        for btn in self.buttons:
            btn.draw(screen)

    def update(self, events):
        self.bgm_slider.update(events)
        self.sfx_slider.update(events)

        settings["vol_bgm"] = self.bgm_slider.get_value()
        settings["vol_sfx"] = self.sfx_slider.get_value()
        pygame.mixer.music.set_volume(settings["vol_bgm"])

        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                for btn in self.buttons:
                    res = btn.handle_event(event)
                    if res:
                        return res
        return None
