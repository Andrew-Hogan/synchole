from tkinter import font
from tkinter import ttk
from tkinter import *
from tkinter import TclError


DEFONT = font.Font(family="Bookman Old Style", size=16, weight="normal")
NORMAL_ATTRS = {'anchor': CENTER, 'background': "#e4e2e0", 'foreground': "#f1f1f1",
                'font': DEFONT, 'relief': FLAT, 'borderwidth': 0, 'padding': (0, 0, 0, 0),
                'highlightthickness': 0}


class MainRoot(Tk):
    def __init__(self):
        Tk.__init__(self)
        self.camera_controller = None
        self.geometry("800x475+200+10")
        self.option_add('*tearOff', False)


def run_example_cam():
    s = ttk.Style()
    s.configure('Normal.TFrame')
    s.configure('Normal.TLabel')
    for style_attribute, value in NORMAL_ATTRS.items():
        minidict = {style_attribute: value}
        s.configure('Normal.TFrame', **minidict)
        s.configure('Normal.TLabel', **minidict)

    return


if __name__ == "__main__":
    run_example_cam()
