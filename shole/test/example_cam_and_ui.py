import sys
from tkinter import font
from tkinter import ttk
from tkinter import *
sys.path.append("..")
sys.path.append("/usr/local/lib/python3.6/site-packages/")
from PIL import ImageTk, Image
import cv2
print(sys.path)

from constants import QURY, SRCE
from drones import cam_process
from managers import GreedyProcessHost

ROOTOMETRY = "800x475+200+10"
BASE_FRAMESTYLE = 'Normal.TFrame'
BASE_LABELSTYLE = 'Normal.TLabel'


class MainRoot(Tk):
    def __init__(self):
        Tk.__init__(self)
        self.camera_controller = None
        self.geometry(ROOTOMETRY)
        self.option_add('*tearOff', False)
        self.current_processor = None
        self.wm_protocol("WM_DELETE_WINDOW", self.on_close)
        self.master_window = None
        self.image_display = None
        self.current_tkimage = None
        self.style_ref = None
        self.source_signal = SRCE
        self.command_signal = QURY
        self.make_application_window()

    def should_interact(self):
        if self.current_processor and self.current_processor.is_running:
            return True
        return False

    def on_close(self):
        if self.should_interact():
            self.current_processor.kill_process()
        self.destroy()

    def make_application_window(self):
        # Start async process.
        self.current_processor = GreedyProcessHost(self, self._message_callback,
                                                   cam_process, 25,
                                                   message_check_delay=40,
                                                   host_to_process_signals={self.source_signal,
                                                                            self.command_signal})

        # Display settings.
        self.style_ref = s = ttk.Style()
        self.set_base_styles(s)

        # Largest frame.
        self.master_window = master_window = ttk.Frame(self, style=BASE_FRAMESTYLE)
        master_window.pack(fill=BOTH, expand=TRUE)

        # Core application organizational split.
        interface_frame = ttk.Frame(master_window, style=BASE_FRAMESTYLE)
        display_frame = ttk.Frame(master_window, style=BASE_FRAMESTYLE)

        interface_frame.grid(column=0, row=2, rowspan=1, columnspan=1, sticky=(N, W, E, S))
        display_frame.grid(column=0, row=0, rowspan=2, columnspan=1, sticky=(N, W, E, S))

        master_window.grid_columnconfigure(0, weight=1)
        master_window.grid_rowconfigure(list(range(3)), weight=1, uniform="ROW_H_RT")

        # Video display.
        self.image_display = ttk.Label(display_frame, style=BASE_LABELSTYLE)
        self.image_display.pack(side=TOP, fill=BOTH, expand=TRUE)

        # Application interface.
        source_button = ttk.Button(interface_frame, command=self._source_button_callback, text="Source")
        query_button = ttk.Button(interface_frame, command=self._query_button_callback, text="Command")

        source_button.pack(side=LEFT, expand=FALSE, fill=None, pady=10)
        query_button.pack(side=RIGHT, expand=FALSE, fill=None, pady=10)

    def _message_callback(self, msg):
        if isinstance(msg, str):
            print("{} message received from process.".format(msg))
        else:
            converted = self.cv2_np_array_to_pil_image(msg)
            self.update_image_display(converted)

    @staticmethod
    def cv2_np_array_to_pil_image(image):
        cv2image = cv2.cvtColor(image, cv2.COLOR_BGR2RGBA)
        pil_image = Image.fromarray(cv2image)
        return pil_image

    def update_image_display(self, image):
        self.current_tkimage = photoimage = ImageTk.PhotoImage(image)
        self.image_display.imgtk = photoimage
        self.image_display.configure(image=photoimage)

    def _source_button_callback(self):
        if self.should_interact():
            self.current_processor.send_signal(self.source_signal)

    def _query_button_callback(self):
        if self.should_interact():
            self.current_processor.send_signal(self.command_signal)


    @staticmethod
    def set_base_styles(style_object):
        defont = font.Font(family="Bookman Old Style", size=16, weight="normal")
        normal_attrs = {'anchor': CENTER, 'background': "#e4e2e0", 'foreground': "#f1f1f1",
                        'font': defont, 'relief': FLAT, 'borderwidth': 0, 'padding': (0, 0, 0, 0),
                        'highlightthickness': 0}
        style_object.configure(BASE_FRAMESTYLE)
        style_object.configure(BASE_LABELSTYLE)
        for style_attribute, value in normal_attrs.items():
            minidict = {style_attribute: value}
            style_object.configure(BASE_FRAMESTYLE, **minidict)
            style_object.configure(BASE_LABELSTYLE, **minidict)


def run_example_cam():
    root = MainRoot()
    root.mainloop()


if __name__ == "__main__":
    run_example_cam()
