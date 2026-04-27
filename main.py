# main.py
import pygame
from config import BGM_TITLE, BGM_MAIN

current_bgm_path = None

def change_bgm(path):
    global current_bgm_path
    if current_bgm_path != path:
        pygame.mixer.music.fadeout(500) # 부드럽게 끄기
        pygame.mixer.music.load(path)
        pygame.mixer.music.play(-1) # 무한 반복
        current_bgm_path = path

# 메인 루프 내부 또는 장면 전환 시점
def main():
    # ...
    while running:
        if state.current_scene == "title":
            change_bgm(BGM_TITLE)
        else:
            change_bgm(BGM_MAIN)
        # ... 나머지 로직