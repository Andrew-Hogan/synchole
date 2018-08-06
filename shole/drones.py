"""Examples and tools for asynchronous processes."""
# USE EXAMPLES & TESTING TO BE COMPLETED.

from time import sleep
import numpy as np
import cv2


KILL = "CLOSE"
DONE = "DONE"
QURY = "QUERY"
SRCE = "SOURCE"


def cam_process(return_queue, command_queue, frame_rate, cam_width, cam_height, *,
                finished_signal=DONE,
                kill_signal=KILL,
                source_signal=SRCE,
                command_signal=QURY,
                set_cam_dimensions=False):
    """Init and start an async camera control process."""
    cam = SyncCam(command_queue, return_queue, frame_rate, kill_signal, source_signal, command_signal,
                  set_cam_dimensions=set_cam_dimensions)
    cam.get_feed(cam_width=cam_width, cam_height=cam_height)
    return_queue.put(finished_signal)


class SyncCam(object):
    """Controls active camera feed."""
    default_camera_number = 0
    default_name = "SyncCam"
    default_filetype = ".png"
    default_width = 800
    default_height = 600
    default_font = cv2.FONT_HERSHEY_SIMPLEX
    default_fill_color = (255, 255, 255)
    default_outline_color = (0, 0, 0)
    default_line_type = cv2.LINE_AA

    def __init__(self, command_queue, return_queue, frame_rate,
                 kill_signal, source_signal, command_signal, *,
                 set_cam_dimensions=False):
        """Set camera control parameters."""
        self.title = self.__class__.default_name
        self.camera_number = self.__class__.default_camera_number
        self.video_capture = None
        self.image_count = 0
        self.camera_number_increment = 1
        self.last_image = None
        self.live_feed = True
        self.command_queue = command_queue
        self.return_queue = return_queue
        self.camera_width = self.__class__.default_width
        self.camera_height = self.__class__.default_height
        self.set_cam_dimensions = set_cam_dimensions
        self.frame_rate = frame_rate
        self.kill_signal = kill_signal
        self.command_signal = command_signal
        self.source_signal = source_signal

    def get_feed(self, cam_width=None, cam_height=None):
        """Slave camera control process."""
        cam_width, cam_height = self._store_cam_dimensions(cam_width, cam_height)
        if self.video_capture is None:
            video_capture = cv2.VideoCapture(self.camera_number)
            if self.set_cam_dimensions:
                video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, cam_width)
                video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_height)
            self.video_capture = video_capture
        while True:
            if not self.command_queue.empty():
                msg = self.command_queue.get()
                should_close = self.react(msg)
                if should_close:
                    break
            rval, frame = self.video_capture.read()
            if self.live_feed:
                if not rval:
                    if self.last_image is None:
                        self.last_image = self.generate_bad_query_image(cam_width, cam_height,
                                                                        query_message="WAITING ON CAM")

                        self.return_queue.put(self.last_image)
                else:
                    self.return_queue.put(frame)
            else:
                if self.last_image is None:
                    self.last_image = self.generate_bad_query_image(cam_width, cam_height,
                                                                    query_message="NO CAMERA")
                self.return_queue.put(self.last_image)
            sleep(self.frame_rate)

    def _store_cam_dimensions(self, cam_width, cam_height):
        if cam_width is None:
            cam_width = self.camera_width
        else:
            self.camera_width = cam_width
        if cam_height is None:
            cam_height = self.camera_height
        else:
            self.camera_height = cam_height
        return cam_width, cam_height

    def react(self, user_input):
        should_close = False
        if user_input == self.source_signal:  # for camera switch.
            self.video_capture, self.camera_number, self.camera_number_increment, replaced = self.camera_cycle(
                self.video_capture, self.camera_number, self.camera_number_increment)
            if replaced and self.camera_number != self.__class__.default_camera_number:
                rval, frame = self.video_capture.read()
            else:
                print("User Warning: Attempted to switch cameras, but could not find another camera.")
                # self.video_capture.release()
                # should_close = True
        elif user_input == self.command_signal:  # for image query mode toggle.
            if self.live_feed:
                if self.video_capture.isOpened():
                    rval, frame = self.video_capture.read()
                    try:
                        processed_image = self.example_camera_command(frame, self.image_count, self.title)
                    except ValueError:
                        image_width = self.video_capture.get(cv2.CAP_PROP_FRAME_WIDTH)
                        image_height = self.video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
                        processed_image = self.generate_bad_query_image(image_width, image_height,
                                                                        query_message="BAD QUERY")
                else:
                    image_width = self.video_capture.get(cv2.CAP_PROP_FRAME_WIDTH)
                    image_height = self.video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
                    processed_image = self.generate_bad_query_image(image_width, image_height,
                                                                    query_message="CAM CLOSED")
                self.last_image = processed_image
                self.live_feed = False
            else:
                self.live_feed = True
        elif user_input == self.kill_signal:
            self.video_capture.release()
            should_close = True
        return should_close

    def camera_cycle(self, video_capture, camera_number, camera_number_increment):
        """Cycle through available cameras sequentially."""
        new_video_capture, new_camera_number = self._get_new_camera(camera_number,
                                                                    camera_number_increment,
                                                                    self.set_cam_dimensions,
                                                                    self.camera_width,
                                                                    self.camera_height)
        video_capture, camera_number, replaced = self._validate_and_replace_new_camera(new_video_capture,
                                                                                       new_camera_number,
                                                                                       video_capture,
                                                                                       camera_number)
        if not (camera_number == 0 or replaced):
            # Potential negative camera numbers.
            if camera_number < 0 < camera_number_increment:
                camera_number_increment = -1
                new_video_capture, new_camera_number = self._get_new_camera(camera_number,
                                                                            camera_number_increment,
                                                                            self.set_cam_dimensions,
                                                                            self.camera_width,
                                                                            self.camera_height)
            else:
                # Restart camera cycle.
                new_video_capture, new_camera_number = self._get_new_camera(0, 0,
                                                                            self.set_cam_dimensions,
                                                                            self.camera_width,
                                                                            self.camera_height)
            video_capture, camera_number, replaced = self._validate_and_replace_new_camera(new_video_capture,
                                                                                           new_camera_number,
                                                                                           video_capture,
                                                                                           camera_number)
        return video_capture, camera_number, camera_number_increment, replaced

    @staticmethod
    def _get_new_camera(camera_number, camera_number_increment, set_dimensions, camera_width, camera_height):
        """Retrieve new camera number and capture from current number and increment direction."""
        new_camera_number = camera_number + camera_number_increment
        new_video_capture = cv2.VideoCapture(new_camera_number)
        if set_dimensions:
            new_video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, camera_width)
            new_video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_height)
        return new_video_capture, new_camera_number

    @staticmethod
    def _validate_and_replace_new_camera(new_video_capture, new_camera_number, video_capture, camera_number):
        """Validate new video capture and potentially replace the existing one - will not import new image from feed."""
        replaced = False
        if new_video_capture is not None and new_video_capture.isOpened():
            video_capture.release()
            camera_number = new_camera_number
            video_capture = new_video_capture
            replaced = True
        return video_capture, camera_number, replaced

    @staticmethod
    def example_camera_command(live_frame, image_count, title, image_filetype=None):
        """Save an image from the camera feed in response to a queue command."""
        if live_frame is None:
            raise ValueError
        else:
            save_name = ''.join((title, "_", str(image_count), image_filetype))
            cv2.imwrite(save_name, live_frame)
        return live_frame

    @classmethod
    def generate_bad_query_image(cls, image_width, image_height, query_message=None,
                                 image_depth=3, default_fill=0,
                                 horizontal_striation_fills=None,
                                 horizontal_striation_points=False,
                                 vertical_striation_fills=((255, 255, 255),
                                                           (127, 127, 127)),
                                 vertical_striation_points=(1 / 3,
                                                            2 / 3)):
        """Generates display in the event of a bad live image query."""
        try:
            image_width = int(image_width)
            image_height = int(image_height)
            default_fill = int(default_fill)
        except ValueError:
            raise
        blank_image = np.full((image_height, image_width, image_depth), fill_value=default_fill, dtype=np.uint8)
        if vertical_striation_points is not False:
            blank_image = cls._striate_image(blank_image, vertical_striation_points, image_width,
                                             vertical_striation_fills, cls._striate_vertical)
        if horizontal_striation_points is not False:
            blank_image = cls._striate_image(blank_image, horizontal_striation_points, image_height,
                                             horizontal_striation_fills, cls._striate_horizontal)
        if query_message is not None:
            output_image = cls.write_bad_query(blank_image, image_width, image_height, message=query_message)
        else:
            output_image = blank_image
        return output_image

    @staticmethod
    def _striate_image(image, relative_striation_points, absolute_size, fill_values, assignment_function):
        """Prints horizontal or vertical striations with fill values at relative locations using function param."""
        previous_absolute_location = 0
        for relative_location, fill_values in zip(relative_striation_points, fill_values):
            absolute_location = int(relative_location * absolute_size)
            try:
                image = assignment_function(image, previous_absolute_location, absolute_location, fill_values)
            except (ValueError, IndexError):
                try:
                    image = assignment_function(image, previous_absolute_location, absolute_location, fill_values[0])
                except (ValueError, IndexError):
                    raise
            previous_absolute_location = absolute_location
        return image

    @staticmethod
    def _striate_vertical(image, start, stop, fill):
        """Prints a vertical striation. Called by _striate_image."""
        image[:, start:stop] = fill
        return image

    @staticmethod
    def _striate_horizontal(image, start, stop, fill):
        """Prints a horizontal striation. Called by _striate_image."""
        image[start:stop, :] = fill
        return image

    @classmethod
    def write_bad_query(cls, image, image_width, image_height, message, font=cv2.FONT_HERSHEY_SIMPLEX, font_scale=1.5,
                        fill_color=(255, 255, 255), outline_color=(0, 0, 0), thickness=2, outline_thickness=4,
                        line_type=cv2.LINE_AA):
        """Places bad query text on image."""
        text_size, _ = cv2.getTextSize(message, fontFace=font, fontScale=font_scale, thickness=thickness)
        text_x = int(max(min((image_width / 2) - (text_size[0] / 2),
                             image_width - text_size[0]),
                         0))
        text_y = int(max(min((image_height / 2) + (text_size[1] / 2),
                             image_height),
                         text_size[1]))
        # Outline.
        cv2.putText(image, message, (text_x, text_y), font, font_scale, outline_color, outline_thickness, line_type)
        # Primary text.
        cv2.putText(image, message, (text_x, text_y), font, font_scale, fill_color, thickness, line_type)
        return image
