import pygame, sys, os

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

pygame.font.init()
FONT = pygame.font.SysFont(None, 36)

width=1280
height=720
white=(255,255,255)
red=(255,0,0)
green=(0,255,0)
blue=(0,0,255)
black=(0,0,0)
fps=30

SIDEBAR_W = 220

CONTENT_X = SIDEBAR_W + 40
CONTENT_Y = 120
CONTENT_W = width - CONTENT_X - 40

ROW_H = 42
VISIBLE_ROWS = 14

SCROLLBAR_W = 12

HEADER_H = 90
MARGIN = 40
GAP = 20

CONTENT_TOP = HEADER_H + GAP
CONTENT_H = height - CONTENT_TOP - MARGIN

LEFT_W = 420
RIGHT_W = width - LEFT_W - MARGIN*2 - GAP

TOP_H = 220
BOTTOM_H = CONTENT_H - TOP_H - GAP

BACK_W = 100
BACK_H = 36

back_x = width - BACK_W - 20
back_y = (HEADER_H - BACK_H) // 2

settings = {
    "vol_bgm": 0.5,
    "vol_sfx": 0.5,
    "difficulty": "Normal",
    "language": "Korean",
    "fps": 60,
    "resolution": "1280x720"
}

DIFFICULTIES = ["Easy", "Normal", "Hard"]
LANGUAGES = ["Korean", "English"]
FPS_OPTIONS = [30, 60, 120]
RESOLUTIONS = ["1280x720", "1600x900", "1920x1080"]
