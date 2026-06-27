from scenes.base_scene import Scene
from ui.button import Button
from config import *
import pygame
from ui.slider import Slider

class OptionScene(Scene):
    def __init__(self, state=None):
        self.state = state
        self.bgm_slider = Slider((410, 395), 200, settings["vol_bgm"])
        self.sfx_slider = Slider((410, 455), 200, settings["vol_sfx"])
        
        self.buttons = [
            # 난이도 변경 버튼
            Button((450, 200, 120, 40), "CHANGE", self.toggle_difficulty),
            # FPS 변경 버튼
            Button((450, 260, 120, 40), "CHANGE", self.toggle_fps),
            # 언어 변경 버튼
            Button((450, 320, 120, 40), "CHANGE", self.toggle_language),
            Button((width//2 - 170, 500, 100, 50), "SAVE", self.save),
            # 뒤로가기
            Button((width//2 - 50, 500, 100, 50), "BACK", self.back)
        ]
        

    def toggle_difficulty(self):
        curr = settings["difficulty"]
        idx = (DIFFICULTIES.index(curr) + 1) % len(DIFFICULTIES)
        settings["difficulty"] = DIFFICULTIES[idx]

    def toggle_fps(self):
        curr = settings["fps"]
        idx = (FPS_OPTIONS.index(curr) + 1) % len(FPS_OPTIONS)
        settings["fps"] = FPS_OPTIONS[idx]
        # 실제 적용하려면 main의 clock.tick(settings["fps"])와 연동 필요

    def toggle_language(self):
        curr = settings["language"]
        idx = (LANGUAGES.index(curr) + 1) % len(LANGUAGES)
        settings["language"] = LANGUAGES[idx]

    def back(self):
        if self.state is not None:
            return getattr(self.state, "prevscene", "title") or "title"
        return "title"

    def save(self):
        return "save_game"

    def draw(self, screen):
        screen.fill((220, 220, 220))
        
        title = FONT.render("OPTIONS", True, black)
        screen.blit(title, (width//2 - 50, 50))

        # 설정 항목 이름과 현재 값 표시
        options_to_show = [
            (f"Difficulty: {settings['difficulty']}", 200),
            (f"FPS: {settings['fps']}", 260),
            (f"Language: {settings['language']}", 320),
            (f"BGM Volume: {int(settings['vol_bgm'] * 100)}%", 380),
            (f"SFX Volume: {int(settings['vol_sfx'] * 100)}%", 440),
        ]

        for text, y in options_to_show:
            txt_surf = FONT.render(text, True, (50, 50, 50))
            screen.blit(txt_surf, (150, y + 5))
            
        #bgm_txt = FONT.render(f"BGM Volume: {int(settings['vol_bgm']*100)}%", True, black)
        #screen.blit(bgm_txt, (100, 380))
        
        #sfx_txt = FONT.render(f"SFX Volume: {int(settings['vol_sfx']*100)}%", True, black)
        #screen.blit(sfx_txt, (100, 440))

        # 슬라이더 그리기
        self.bgm_slider.draw(screen)
        self.sfx_slider.draw(screen)

        for btn in self.buttons:
            btn.draw(screen)
            
    def update(self, events):
        # 슬라이더 업데이트
        self.bgm_slider.update(events)
        self.sfx_slider.update(events)
        
        # 실시간 볼륨 적용
        settings["vol_bgm"] = self.bgm_slider.get_value()
        settings["vol_sfx"] = self.sfx_slider.get_value()
        pygame.mixer.music.set_volume(settings["vol_bgm"])

        # 버튼 업데이트 (기존 로직)
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                for btn in self.buttons:
                    res = btn.handle_event(event)
                    if res: return res
        return None
    
    
