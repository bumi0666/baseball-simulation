import tkinter as tk
import random

def stat_color(value):
    if value>=80:
        return "red"
    elif value>=60:
        return "green"
    else:
        return "black"


class GameConfig:
    def __init__(self):
        self.difficulty="중간"
        self.speed=3

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Demo")
        self.geometry("640x400")
        self.resizable(False, False)
        self.frames={}
        
        self.config_data = GameConfig()
        
        self.team_data = {
        "batters": [
        {
            "name": "김타자",
            "pos": "CF",
            "avg": 0.280,
            "power": 65,
            "defense": 70
        },
        {
            "name": "이타자",
            "pos": "2B",
            "avg": 0.310,
            "power": 50,
            "defense": 75
        }
        ],
        "pitchers": [
        {
            "name": "홍투수",
            "role": "선발",
            "era": 3.20,
            "control": 70,
            "stamina": 80
        },
        {
            "name": "윤투수",
            "role": "불펜",
            "era": 2.90,
            "control": 75,
            "stamina": 60
        }
        ]   
        }
        
        for Frames in (MainFrame, BattleFrame, SettingFrame, TeamManageFrame):
            frame=Frames(self)
            frame.place(relwidth=1, relheight=1)
            self.frames[Frames]=frame
            
        self.show(MainFrame)

    def show(self, whatframe):
        self.frames[whatframe].tkraise()

        

class MainFrame(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        label=tk.Label(self, text="This is main.")
        label.place(x=20,y=20)

        play_button=tk.Button(self, text="대결", overrelief="solid", width=20, height=2, command=lambda: master.show(BattleFrame))
        play_button.place(x=20,y=60)

        manage_button=tk.Button(self, text="팀 관리", overrelief="solid", width=20, height=2, command=lambda: master.show(TeamManageFrame))
        manage_button.place(x=20,y=120)

        stat_button=tk.Button(self, text="기록", overrelief="solid", width=20, height=2)
        stat_button.place(x=20,y=180)

        setting_button=tk.Button(self, text="설정", overrelief="solid", width=20, height=2, command=lambda: master.show(SettingFrame))
        setting_button.place(x=20,y=240)

        end_button=tk.Button(self, text="종료", overrelief="solid", width=20, height=2, command=self.master.destroy)
        end_button.place(x=20,y=300)
        

class BattleFrame(tk.Frame):
    def __init__(self, master):
        super().__init__(master)

        tk.Label(self, text="대결", font=("Arial", 14, "bold")).place(x=20, y=20)

        self.score_label = tk.Label(self, text="플레이어 0 : 0 상대", font=("Arial", 12))
        self.score_label.place(x=20, y=60)

        self.log = tk.Listbox(self, width=60, height=12)
        self.log.place(x=20, y=100)

        tk.Button(self, text="다음 플레이", width=15, command=self.next_play).place(x=20, y=330)
        tk.Button(self, text="종료", width=15,
                  command=lambda: master.show(MainFrame)).place(x=200, y=330)

        self.inning=1
        self.half="top"
        self.score=[0,0]
        
        self.outs=0
        self.base=[0,0,0]
        
    def next_play(self):
        result=random.choice(["아웃", "1루타", "2루타", "홈런", "삼진"])

        team="초" if self.half=="top" else "말"
        self.log.insert(tk.END, f"{self.inning}회 {team}: {result}")
        self.log.yview(tk.END)

        if result in ("아웃","삼진"):
            self.outs+=1
            
        if result=="안타":
            if self.half=="top":
                self.score[1]+=1
            else:
                self.score[0]+=1
            
            
        if result=="홈런":
            if self.half == "top":
                self.score[1] += 1
            else:
                self.score[0] += 1

        if self.outs >= 3:
            self.outs = 0
            if self.half == "top":
                self.half = "bottom"
            else:
                self.half = "top"
                self.inning += 1

        self.score_label.config(
            text=f"{self.inning}회 | 플레이어 {self.score[0]} : {self.score[1]} 상대"
        )


        
        
class TeamManageFrame(tk.Frame):
    def __init__(self, master):
        super().__init__(master)

        tk.Label(self, text="팀 관리").place(x=20, y=20)

        tk.Button(self, text="타자", width=10, command=self.show_batters).place(x=20, y=50)
        tk.Button(self, text="투수", width=10, command=self.show_pitchers).place(x=120, y=50)

        self.listbox = tk.Listbox(self, width=25, height=12)
        self.listbox.place(x=20, y=90)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        self.info_labels = {}
        y=90
        for key in ("이름", "포지션", "타율/ERA", "파워/제구", "수비/체력"):
            lbl=tk.Label(self, text="")
            lbl.place(x=300, y=y)
            self.info_labels[key]=lbl
            y+=30

        self.current = []
        self.show_batters()
        
    def show_batters(self):
        self.current = self.master.team_data["batters"]
        self.refresh_list()

    def show_pitchers(self):
        self.current = self.master.team_data["pitchers"]
        self.refresh_list()
        
    def refresh_list(self):
        self.listbox.delete(0, tk.END)
        for p in self.current:
            self.listbox.insert(tk.END, p["name"])
        
    def on_select(self, event):
        if not self.listbox.curselection():
            return

        idx=self.listbox.curselection()[0]
        p=self.current[idx]

        if "pos" in p:
            self.info_labels["이름"].config(text=f"이름: {p['name']}")
            self.info_labels["포지션"].config(text=f"포지션: {p['pos']}")
            self.info_labels["타율/ERA"].config(text=f"타율: {p['avg']}")
            self.info_labels["파워/제구"].config(text=f"파워: {p['power']}",fg=stat_color(int(p['power'])))
            self.info_labels["수비/체력"].config(text=f"수비: {p['defense']}",fg=stat_color(int(p['defense'])))
        else:
            self.info_labels["이름"].config(text=f"이름: {p['name']}")
            self.info_labels["포지션"].config(text=f"역할: {p['role']}")
            self.info_labels["타율/ERA"].config(text=f"ERA: {p['era']}")
            self.info_labels["파워/제구"].config(text=f"제구: {p['control']}",fg=stat_color(int(p['control'])))
            self.info_labels["수비/체력"].config(text=f"체력: {p['stamina']}",fg=stat_color(int(p['stamina'])))


class SettingFrame(tk.Frame):
    def __init__(self, master):
        super().__init__(master)

        tk.Label(self, text="설정 화면").place(x=20, y=20)
        
        tk.Label(self, text="난이도:").place(x=20, y=60)
        self.listbox=tk.Listbox(self, selectmode='single', height=3)
        self.listbox.place(x=100,y=60)
        
        levels = ["쉬움", "중간", "어려움"]
        
        self.listbox.insert(0,"쉬움")
        self.listbox.insert(1,"중간")
        self.listbox.insert(2,"어려움")
        
        now=self.master.config_data.difficulty
        if now in levels:
            self.listbox.select_set(levels.index(now))
        
        tk.Label(self, text="경기 속도(1~10):").place(x=20, y=140)
        self.entry=tk.Entry(self)
        self.entry.place(x=120,y=140)
        self.entry.insert(0, self.master.config_data.speed)
        
        save_button=tk.Button(self, text="저장 후 종료", overrelief="solid", width=20, height=2, command=self.save_setting )
        save_button.place(x=20,y=300)
            
    def save_setting(self):
        
        value=self.entry.get()
        if value.isdigit() and int(value)>=1 and int(value)<=10:
            self.master.config_data.speed=int(value)
        else:
            self.entry.delete(0,tk.END)
            self.entry.insert(0,self.master.config_data.speed)
            return
            
        sel=self.listbox.curselection()
        if not sel:
            print("난이도 선택 안 됨")
            return

        difficulty=self.listbox.get(sel[0])
        self.master.config_data.difficulty=difficulty
        print("저장된 난이도:", difficulty)
        print("저장된 경기 속도:",self.master.config_data.speed)
        
        self.master.show(MainFrame) 
        

if __name__=="__main__":
    App().mainloop()

