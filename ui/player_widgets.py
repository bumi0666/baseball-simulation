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
