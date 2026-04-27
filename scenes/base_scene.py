import pygame

class Scene:
    def update(self, events):
        mouse_pos = None
        try:
            mouse_pos = pygame.mouse.get_pos()
        except:
            pass

        for btn in getattr(self, "buttons", []):
            btn.update_hover(mouse_pos)

        for e in events:
            for btn in getattr(self, "buttons", []):
                result = btn.handle_event(e)
                if result:
                    return result
        return None

    def draw(self, screen):
        pass
