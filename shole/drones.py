"""Examples and tools for asynchronous processes."""
# USE EXAMPLES & TESTING TO BE COMPLETED.

from time import sleep
import numpy as np
import cv2
from constants import KILL, DONE, QURY, SRCE


def cam_process(return_queue, command_queue, frame_rate, cam_width=None, cam_height=None, *,
                finished_signal=DONE,
                kill_signal=KILL,
                source_signal=SRCE,
                command_signal=QURY,
                set_cam_dimensions=False):
    """
    Init and start an async camera control process.

    :Parameters:
        :param multiprocessing.Queue return_queue: queue for all communications to the host process.
        :param multiprocessing.Queue command_queue: queue for communications from the host process to this process.
        :param int frame_rate: determines how often a frame is pulled from the camera.
        :param int cam_width: determines how wide the camera frame is if set_cam_dimensions is True.
        :param int cam_height: determines how tall the camera frame is if set_cam_dimensions is True.
        :param str finished_signal: message to be used to indicate that this process finished.
        :param str kill_signal: message to be used to finish this process early.
        :param str source_signal: message to be used to change the camera source.
        :param str command_signal: message to be used to trigger a predetermined process on a camera frame.
        :param bool set_cam_dimensions: determines if camera frame dimensions are set using OpenCV.
    :rtype: None
    :return: None
    """
    cam = SyncCam(command_queue, return_queue, frame_rate, kill_signal, source_signal, command_signal,
                  set_cam_dimensions=set_cam_dimensions)
    cam.get_feed(cam_width=cam_width, cam_height=cam_height)
    return_queue.put(finished_signal)


class SyncCam(object):
    """
    Controls active camera feed.

    :cvar int default_camera_number: starting camera source number.
    :cvar str default_name: default value for self.title used in the example camera command for file save names.
    :cvar str default_filetype: default file ending used in the example camera command for saving images.
    :cvar int default_width: default camera width to be used if modifying the camera frame dimensions.
    :cvar int default_height: default camera height to be used if modifying the camera frame dimensions.
    """
    default_camera_number = 0
    default_name = "SyncCam"
    default_width = 800
    default_height = 600

    def __init__(self, command_queue, return_queue, frame_rate,
                 kill_signal, source_signal, command_signal, *,
                 set_cam_dimensions=False):
        """
        Set camera control parameters.

        :Parameters:
            :param multiprocessing.Queue command_queue: queue for communications from the host process to this process.
            :param multiprocessing.Queue return_queue: queue for all communications to the host process.
            :param int frame_rate: determines how often a frame is pulled from the camera.
            :param str kill_signal: message to be used to finish this process early.
            :param str source_signal: message to be used to change the camera source.
            :param str command_signal: message to be used to trigger a predetermined process on a camera frame.
            :param bool set_cam_dimensions: determines if a camera frame dimensions are set using OpenCV.
        :rtype: None
        :return: None
        """
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
        """
        Start / maintain slave camera control process.

        :Parameters:
            :param int or None cam_width: determines how wide the camera frame is if self.set_cam_dimensions is True.
            :param int or None cam_height: determines how tall the camera frame is if self.set_cam_dimensions is True.
        :rtype: None
        :return: None
        """
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
        """
        Set and return instance attributes from supplied cam_width / cam_height.

        :Parameters:
            :param int or None cam_width: determines how wide the camera frame is if self.set_cam_dimensions is True.
            :param int or None cam_height: determines how tall the camera frame is if self.set_cam_dimensions is True.
        :rtype: tuple of int, int
        :returns:
            :return int cam_width: determines how wide the camera frame is if self.set_cam_dimensions is True.
            :return int cam_height: determines how tall the camera frame is if self.set_cam_dimensions is True.
        """
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
        """
        Interpret input from the host process.

        :Parameters:
            :param user_input: command from the host process to be interpreted.
        :rtype: bool
        :return bool should_close: determines if the camera & this process should remain open & running.
        """
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
        """
        Cycle through available cameras sequentially.

        :Parameters:
            :param video_capture: OpenCV VideoCapture instance currently being controlled by this instance.
            :param int camera_number: the current camera source number.
            :param int camera_number_increment: the direction camera_number is incremented while cycling.
        :rtype: tuple of cv2.VideoCapture, int, int, bool
        :returns:
            :return video_capture: OpenCV VideoCapture instance currently being controlled by this instance.
            :return int camera_number: the current camera source number.
            :return int camera_number_increment: the direction camera_number is incremented while cycling.
            :return bool replaced: whether the camera source was changed by this method.
        """
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
        """
        Retrieve new camera number and capture from current number and increment direction.

        :Parameters:
            :param int camera_number: the current camera source number.
            :param int camera_number_increment: the direction camera_number is incremented while cycling.
            :param bool set_dimensions: determines if camera frame dimensions are set using OpenCV.
            :param int camera_width: determines how wide the camera frame is if set_dimensions is True.
            :param int camera_height: determines how tall the camera frame is if set_dimensions is True.
        :rtype: tuple of cv2.VideoCapture, int
        :returns:
            :return new_video_capture: newly created OpenCV VideoCapture instance.
            :return int new_camera_number: camera source number of the newly created OpenCV VideoCapture instance.
        """
        new_camera_number = camera_number + camera_number_increment
        new_video_capture = cv2.VideoCapture(new_camera_number)
        if set_dimensions:
            new_video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, camera_width)
            new_video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_height)
        return new_video_capture, new_camera_number

    @staticmethod
    def _validate_and_replace_new_camera(new_video_capture, new_camera_number, video_capture, camera_number):
        """
        Validate new video capture and potentially replace the existing one - will not import new image from feed.

        :Parameters:
            :param new_video_capture: cv2.VideoCapture instance to be validated.
            :param int new_camera_number: camera source number of the new_video_capture instance.
            :param video_capture: cv2.VideoCapture instance currently being controlled by this instance.
            :param int camera_number: camera source number of the video_capture instance.
        :rtype: tuple of cv2.VideoCapture, int, bool
        :returns:
            :return video_capture: the cv2.VideoCapture instance which is/will now be controlled by this instance.
            :return int camera_number: the camera source number of the video_capture instance.
            :return bool replaced: whether or not the video_capture instance was closed & changed.
        """
        replaced = False
        if new_video_capture is not None and new_video_capture.isOpened():
            video_capture.release()
            camera_number = new_camera_number
            video_capture = new_video_capture
            replaced = True
        return video_capture, camera_number, replaced

    @staticmethod
    def example_camera_command(live_frame, image_count, title, image_filetype='.png'):
        """
        Save an image from the camera feed in response to a queue command.

        :Parameters:
            :param numpy.array live_frame: the image pulled from the current camera.
            :param int image_count: the number of images already saved by this instance.
            :param str title: the file name prefix to be used when saving the current frame.
            :param str image_filetype: the file name suffix to be used when saving the current frame.
        :rtype: numpy.array
        :return numpy.array live_frame: the image pulled from the current camera.
        """
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
        """
        Generates display in the event of a bad live image query.

        :Parameters:
            :param int image_width: the width of the bad query image to be generated.
            :param int image_height: the height of the bad query image to be generated.
            :param str or None query_message: the message to be written on the bad query image.
            :param int image_depth: the number of color channels to be created in the resulting np.array.
            :param int default_fill: the default fill value of the resulting numpy.array.
            :param tuple or None horizontal_striation_fills: tuples of (int,) * image_depth to be used as fill values
                for horizontal striations.
            :param tuple or None horizontal_striation_points: tuple of floats in the range of (0, 1) determining
                relative image locations to be striated horizontally.
            :param tuple or None vertical_striation_fills: tuples of (int,) * image_depth to be used as fill values
                for vertical striations.
            :param tuple or None vertical_striation_points: tuple of floats in the range of (0, 1) determining
                relative image locations to be striated vertically.
        :rtype: numpy.array
        :return numpy.array output_image: the generated bad query image.
        """
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
        """
        Prints horizontal or vertical striations with fill values at relative locations using function param.

        :Parameters:
            :param numpy.array image: the image to be striated.
            :param tuple of floats relative_striation_points: tuple of floats in the range of (0, 1) determining
                relative image locations to be striated horizontally.
            :param int absolute_size: the length of image along the dimension to be striated.
            :param list of tuple of ints fill_values: the fill values to be used in striation,
                with a list of len(relative_striation_points) and tuples of the same length as image depth.
            :param function assignment_function: striation function or method to be called per relative striation.
        :rtype: numpy.array
        :return numpy.array image: the image with striations applied.
        """
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
        """
        Prints a vertical striation. Called by _striate_image.

        :Parameters:
            :param numpy.array image: the image to be striated.
            :param int start: the starting slice index for applying the fill value.
            :param int stop: the stopping slice index for applying the fill value.
            :param tuple of ints fill: tuple of ints of the same length as the image depth to be used as a fill value.
        :rtype: numpy.array
        :return numpy.array image: the image with a vertical striation applied.
        """
        image[:, start:stop] = fill
        return image

    @staticmethod
    def _striate_horizontal(image, start, stop, fill):
        """
        Prints a horizontal striation. Called by _striate_image.

        :Parameters:
            :param numpy.array image: the image to be striated.
            :param int start: the starting slice index for applying the fill value.
            :param int stop: the stopping slice index for applying the fill value.
            :param tuple of ints fill: tuple of ints of the same length as the image depth to be used as a fill value.
        :rtype: numpy.array
        :return numpy.array image: the image with a horizontal striation applied.
        """
        image[start:stop, :] = fill
        return image

    @classmethod
    def write_bad_query(cls, image, image_width, image_height, message, font=cv2.FONT_HERSHEY_SIMPLEX, font_scale=1.5,
                        fill_color=(255, 255, 255), outline_color=(0, 0, 0), thickness=2, outline_thickness=4,
                        line_type=cv2.LINE_AA):
        """
        Places bad query text on image.

        :Parameters:
            :param numpy.array image: the image to have the bad query message written on it.
            :param int image_width: the width of the image to be used for placing text. (Text is placed in center.)
            :param int image_height: the height of the image to be used for placing text. (Text is placed in center.)
            :param str message: the message to be written on image.
            :param font: the OpenCV font to be used for writing message.
            :param float font_scale: the font scale to be passed to cv2.putText and cv2.getTextSize.
            :param tuple of (int,) * image depth fill_color: the text fill color to be used.
            :param tuple of (int,) * image depth outline_color: the text outline color to be used.
            :param int thickness: font thickness to be passed to cv2.putText and cv2.getTextSize.
            :param int outline_thickness: font thickness to be used for the text outline in cv2.putText.
            :param line_type: the OpenCV line type to be used for writing message.
        :rtype: numpy.array
        :return numpy.array image: the image with a bad query message overlaid on it.
        """
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
