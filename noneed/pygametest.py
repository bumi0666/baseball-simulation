import pygame
import sys, random
from pygame.locals import *

width=600
height=400
white=(255,255,255)
red=(255,0,0)
green=(0,255,0)
blue=(0,0,255)
black=(0,0,0)
fps=30

pygame.init()

pygame.display.set_caption('Developing...')
screen=pygame.display.set_mode((width, height))

class Dino:
    def __init__(self):
        self.rect=pygame.Rect(50,300,40,40)
        self.jumping=False
        self.velocity_y=0
        
    def jump(self):
        if not self.jumping:
            self.jumping=True
            self.velocity_y=-10
            
    def update(self):
        self.rect.y+=self.velocity_y
        self.velocity_y+=0.6
        
        if self.rect.y>300:
            self.rect.y=300
            self.jumping=False
            self.velocity_y=0

class Obstacle:
    def __init__(self):
        self.rect=pygame.Rect(width,300,40,40)

    def update(self):
        self.rect.x-=5
#gulimfont=pygame.font.SysFont('굴림',70)
#helloworld=gulimfont.render('Hello, world!',1,black) 
#hellorect=helloworld.get_rect()
#hellorect.center=(width/2,height/2) 
 

def main():
    clock=pygame.time.Clock()
    dino=Dino()
    obstacles=[]
    ts=0
    last=0
    while True:
        screen.fill(white)
        for event in pygame.event.get():
            if event.type==pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type==pygame.KEYDOWN:
                if event.key==pygame.K_SPACE:
                    dino.jump()
                    
        if random.randint(1,100)<=3 and ts-last>=40:
            print(last,ts)
            obstacles.append(Obstacle())
            last=ts
        
        for obs in obstacles[:]:
            obs.update()
            if obs.rect.x<=-40:
                obstacles.remove(obs)
            if dino.rect.colliderect(obs):
                pygame.quit()
                sys.exit()
            
            
            
        dino.update()
        pygame.draw.rect(screen,green,dino.rect)
        for obs in obstacles:
            pygame.draw.rect(screen,red,obs.rect)
        pygame.display.flip()
    #displaysurf.blit(helloworld, hellorect)
    
    #pygame.display.update() partly update
        clock.tick(fps)
        ts+=1
    
    
if __name__=="__main__":
    main()