"""Basic toolkit for asynchronous task communication / management using friendly threaded queues."""
# USE EXAMPLES & TESTING TO BE COMPLETED.

from threading import Thread
from multiprocessing import Pool, Process
from multiprocessing.context import TimeoutError as TimesUpPencilsDown
from multiprocessing import Queue as MultiQueue
from queue import Queue
from queue import Empty as EmptyQueue
from constants import KILL, DONE, CZEC


def clear_and_close_queues(*queues):
    """
    Close an arbitrary-length tuple of multiprocessing and queue lib queue(s).

    :Parameters:
        :param queues: queue.Queues and/or multiprocessing.Queues to be cleared and closed.
    :rtype: None
    :return: None
    """
    for queue in queues:
        clear_queues(queue)
        try:
            queue.close()
        except AttributeError:
            with queue.mutex:
                queue.queue.clear()


def clear_queues(*queues):
    """
    Remove remaining items in an arbitrary-length tuple of multiprocessing and queue lib queue(s).

    :Parameters:
        :param queues: queue.Queues and/or multiprocessing.Queues to be cleared.
    :rtype: None
    :return: None
    """
    for queue in queues:
        try:
            while not queue.empty():
                _ = queue.get()
        except OSError:
            pass


class ProcessHost(object):
    """
    Multiprocessing/threading object which can be accessed directly within libraries like Tkinter.

    Send a target function to an instance of this class during __init__ or make_single_process_handler, and it will
    ensure the process completes, and pass any queue return messages to the function provided in message_callback
    during __init__.
    """
    def __init__(self, root, message_callback, process_target=None, *process_args,
                 message_check_delay=1000,
                 running_check_delay=10000,
                 run_process=True,
                 host_to_process_signals=None,
                 finished_signal=DONE,
                 kill_signal=KILL,
                 check_signal=CZEC,
                 **process_kwarg_dict):
        """Create private inter-process communication for a potentially newly started process.

        :Parameters:
            :param Tkinter.Tk root: root / object with .after(delay, callback) used for scheduling.
            :param function message_callback: function / method used to process a message if received.
            :param function process_target: function / method to be run asynchronously.
            :param process_args: positional arguments to be passed to process_target.
            :param int message_check_delay: how often message checks are scheduled using root.
            :param int running_check_delay: how often checks on whether the subprocess is running are run.
            :param bool run_process: determines whether to run the process_target immediately after __init__.
            :param set host_to_process_signals: messages for the asynchronous process which may be sent to the handler.
            :param str finished_signal: message to be used to indicate that the asynchronous process finished.
            :param str kill_signal: message to be used to finish the asynchronous process early.
            :param str check_signal: message to be used to check if the asynchronous process is still alive.
            :param process_kwarg_dict: dictionary to be passed to process_target.
        :rtype: None
        :return: None
        """
        self.root = root
        self.message_check_rate = message_check_delay
        self.running_check_delay = running_check_delay
        self.message_callback = message_callback
        self._to_host_queue = Queue()  # Please respect the privacy of these attributes. Altering them without
        self._to_handler_queue = MultiQueue()  # consideration for processes relying on their private state can have
        self.kill_signal = kill_signal  # unintended process opening / closing, especially with reuse.
        self.finished_signal = finished_signal
        self.check_signal = check_signal
        self.is_running = False
        self._continue_running = run_process
        self._current_processor = None
        assert (self.kill_signal
                != self.finished_signal
                != self.check_signal
                != self.finished_signal), "Use unique built-in queue signals."
        self.process_end_signals = {self.kill_signal, self.finished_signal, self.check_signal}
        if process_target is not None and run_process:
            self.make_single_process_handler(process_target,
                                             *process_args,
                                             host_to_process_signals=host_to_process_signals,
                                             **process_kwarg_dict)

    def make_single_process_handler(self, process_target, *process_args,
                                    host_to_process_signals=None,
                                    **process_kwarg_dict):
        """
        Create a process handler and Tkinter threads for process callbacks.

        :Parameters:
            :param function process_target: function / method to be run asynchronously.
            :param process_args: positional arguments to be passed to process_target.
            :param set host_to_process_signals: messages for the asynchronous process which may be sent to the handler.
            :param process_kwarg_dict: dictionary to be passed to process_target.
        :rtype: None
        :return: None
        """
        assert not self.is_running, ("Please create a new SingleProcessHandler to start another process while this one "
                                     "is still running.")
        _handler_to_process_queue = MultiQueue() if host_to_process_signals else None
        self._continue_running = True
        self.is_running = True
        self._current_processor = SingleProcessHandler(process_target,
                                                       self._to_handler_queue,
                                                       self._to_host_queue, *process_args,
                                                       handler_to_process_queue=_handler_to_process_queue,
                                                       finished_signal=self.finished_signal,
                                                       kill_signal=self.kill_signal,
                                                       check_signal=self.check_signal,
                                                       host_to_process_signals=host_to_process_signals,
                                                       **process_kwarg_dict)
        self._current_processor.start()
        self.root.after(self.message_check_rate, self.check_message)
        self.root.after(self.running_check_delay, self.check_running)

    def send_signal(self, signal):
        """
        Send signal to other process.

        :Parameters:
            :param signal: pickle-able object sent to subprocess.
        :rtype: None
        :return: None
        """
        self._to_handler_queue.put(signal)

    def check_message(self, *, message_callback=None):
        """
        Initiate callbacks from inter-process communication.

        :Parameters:
            :param function message_callback: function / method used to process a message if received. Currently
                determines if check_message is subsequently called as well. If intending to check for a message
                independent of the auto-check (and not intending to start another check_message thread chain)
                pass self.message_callback or any other function as a parameter to prevent the check_message chain.
        :rtype: None
        :return: None
        """
        if message_callback is None:
            say_check_one_more_time = self._continue_running
            message_callback = self.message_callback
        else:
            say_check_one_more_time = False
        try:
            if not self._to_host_queue.empty():
                try:
                    msg = self._to_host_queue.get_nowait()
                except EmptyQueue:
                    pass
                else:
                    if isinstance(msg, str):
                        # print("{} for host.".format(msg))
                        if msg in self.process_end_signals:
                            say_check_one_more_time = False
                            self.kill_process(need_to_signal=False)
                    message_callback(msg)
                finally:
                    if say_check_one_more_time:
                        self.root.after(self.message_check_rate, self.check_message)
            elif say_check_one_more_time:
                self.root.after(self.message_check_rate, self.check_message)
        except AttributeError:
            self.kill_process()

    def kill_process(self, *, need_to_signal=True):
        """
        End current process / clear queues.

        :Parameters:
            :param bool need_to_signal: determines if a signal is sent to the process handler to end. Needs to be
                True unless a signal has already been sent to the process handler.
        :rtype: None
        :return: None
        """
        self._continue_running = False
        if (self._current_processor is not None
                and self._current_processor.is_alive()):
            if need_to_signal:
                self._to_handler_queue.put(self.kill_signal)
                clear_queues(self._to_host_queue)
            self._current_processor.join()
        clear_queues(self._to_host_queue, self._to_handler_queue)
        self._current_processor = None
        self.is_running = False

    def check_running(self):
        """
        Maintain communication with subprocess to ensure it's running.

        :rtype: None
        :return: None
        """
        if (self._continue_running
                and self._current_processor is not None
                and self._current_processor.is_alive()):
            self._to_handler_queue.put(self.check_signal)
            self.root.after(self.running_check_delay, self.check_running)


class GreedyProcessHost(ProcessHost):
    """
    Multiprocessing/threading object which can be accessed directly within libraries like Tkinter.

    Send a target function to an instance of this class during __init__ or make_single_process_handler, and it will
    ensure the process completes, and pass the most recent queue return messages to the function provided in
    message_callback during __init__ - while keeping the rest to itself. (Rude.)
    """
    def __init__(self, *args, **kwargs):
        """Create private inter-process communication for a potentially newly started process.

        :Parameters:
            :param Tkinter.Tk root: root / object with .after(delay, callback) used for scheduling.
            :param function message_callback: function / method used to process the most recent message if received.
            :param function process_target: function / method to be run asynchronously.
            :param process_args: positional arguments to be passed to process_target.
            :param int message_check_delay: how often message checks are scheduled using root.
            :param int running_check_delay: how often checks on whether the subprocess is running are run.
            :param bool run_process: determines whether to run the process_target immediately after __init__.
            :param set host_to_process_signals: messages for the asynchronous process which may be sent to the handler.
            :param str finished_signal: message to be used to indicate that the asynchronous process finished.
            :param str kill_signal: message to be used to finish the asynchronous process early.
            :param str check_signal: message to be used to check if the asynchronous process is still alive.
            :param process_kwarg_dict: dictionary to be passed to process_target.
        :rtype: None
        :return: None
        """
        super(GreedyProcessHost, self).__init__(*args, **kwargs)

    def check_message(self, *, message_callback=None):
        """
        Initiate callbacks from inter-process communication. Overwrites the original check_message method in order
        to only pull the most recent queue item.

        :Parameters:
            :param function message_callback: function / method used to process a message if received. Currently
                determines if check_message is subsequently called as well. If intending to check for a message
                independent of the auto-check (and not intending to start another check_message thread chain)
                pass self.message_callback or any other function as a parameter to prevent the check_message chain.
        :rtype: None
        :return: None
        """
        if message_callback is None:
            say_check_one_more_time = self._continue_running
            message_callback = self.message_callback
        else:
            say_check_one_more_time = False
        try:
            if not self._to_host_queue.empty():
                msg = None
                try:
                    while not self._to_host_queue.empty():
                        msg = self._to_host_queue.get_nowait()
                except EmptyQueue:
                    pass
                else:
                    if isinstance(msg, str):
                        # print("{} for greedy host.".format(msg))
                        if msg in self.process_end_signals:
                            say_check_one_more_time = False
                            self.kill_process(need_to_signal=False)
                    message_callback(msg)
                finally:
                    if say_check_one_more_time:
                        self.root.after(self.message_check_rate, self.check_message)
            elif say_check_one_more_time:
                self.root.after(self.message_check_rate, self.check_message)
        except AttributeError:
            self.kill_process()


class SingleProcessHandler(Thread):
    """Manages single asynchronous processes - nothing in this object should be interacted with directly."""
    def __init__(self, process_target, to_handler_queue, handler_to_host_queue, *process_args,
                 handler_to_process_queue=None,
                 finished_signal=DONE,
                 kill_signal=KILL,
                 check_signal=CZEC,
                 host_to_process_signals=None,
                 **process_kwarg_dict):
        """
        Set runtime attributes for multi-process communication / management.

        :Parameters:
            :param function process_target: function / method to be run asynchronously.
            :param multiprocessing.Queue to_handler_queue: queue for all communications sent to this class instance.
            :param queue.Queue handler_to_host_queue: queue for communications to the host process from this instance.
            :param process_args: positional arguments to be passed to process_target.
            :param multiprocessing.Queue handler_to_process_queue: queue for communications from the host process
                to the running asynchronous process_target.
            :param str finished_signal: message to be used to indicate that the asynchronous process finished.
            :param str kill_signal: message to be used to finish the asynchronous process early.
            :param str check_signal: message to be used to check if the asynchronous process is still alive.
            :param set host_to_process_signals: messages for the asynchronous process which may be sent to the handler.
            :param process_kwarg_dict: dictionary to be passed to process_target.
        :rtype: None
        :return: None
        """
        Thread.__init__(self)
        self.host_to_process_signals = host_to_process_signals if host_to_process_signals else {}
        self.kill_signal = kill_signal
        self.finished_signal = finished_signal
        self.check_signal = check_signal
        assert (self.kill_signal
                != self.finished_signal
                != self.check_signal
                != self.kill_signal), "Use unique built-in queue signals."
        self.end_sigs = {self.kill_signal, self.finished_signal}
        self.handler_to_host_queue = handler_to_host_queue
        self.handler_to_process_queue = handler_to_process_queue
        self.to_handler_queue = to_handler_queue
        self.process_target = process_target
        self.process_args = None
        self._import_process_args(process_args, process_kwarg_dict)
        self.handled_process = None

    def _import_process_args(self, process_args=None, process_kwarg_dict=None):
        """
        Create the tuple of process args needed for multiprocessing.Process.

        :Parameters:
            :param process_args: positional arguments to be passed to process_target.
            :param process_kwarg_dict: dictionary to be passed to process_target.
        :rtype: None
        :return: None
        """
        if process_args and process_kwarg_dict:
            self.process_args = process_args + (process_kwarg_dict,)
        elif process_args:
            self.process_args = process_args
        elif process_kwarg_dict:
            self.process_args = (process_kwarg_dict,)
        if self.handler_to_process_queue:
            if self.process_args:
                self.process_args = (self.to_handler_queue, self.handler_to_process_queue) + self.process_args
            else:
                self.process_args = (self.to_handler_queue, self.handler_to_process_queue)
        elif self.process_args:
            self.process_args = (self.to_handler_queue,) + self.process_args
        else:
            self.process_args = (self.to_handler_queue,)

    def run(self):
        """
        Start / maintain process communication.

        :rtype: None
        :return: None
        """
        self.handled_process = Process(target=self.process_target,
                                       args=self.process_args)
        self.handled_process.start()
        should_run = True
        while should_run:
            should_run = self._process_queues()

    def _process_queues(self):
        """
        Transmit / interpret signals between processes.

        :rtype: bool
        :return bool should_run: determine whether the run() loop should continue.
        """
        should_run = True
        msg = self.to_handler_queue.get()
        if isinstance(msg, str):
            # print("{} for handler.".format(msg))
            if msg in self.end_sigs:
                self._kill_process()
                self.handler_to_host_queue.put(msg)
                should_run = False
            elif msg == self.check_signal:
                if not self.handled_process.is_alive():
                    self.handler_to_host_queue.put(msg)
                    should_run = False
            elif msg in self.host_to_process_signals:
                self.handler_to_process_queue.put(msg)
            else:
                self.handler_to_host_queue.put(msg)
        else:
            self.handler_to_host_queue.put(msg)
        return should_run

    def _kill_process(self):
        """
        Handle queue / process cleanup for end-process signals.

        :rtype: None
        :return: None
        """
        if self.handled_process is not None:
            if self.handler_to_process_queue:
                self._okay_maybe_some_tears_but_be_quick()
            else:
                self._shh_no_more_tears(self.handled_process, self.to_handler_queue)
            self.handled_process = None

    def _okay_maybe_some_tears_but_be_quick(self):
        """
        Close process while allowing for one to-process-queue signal for cleanup.

        :rtype: None
        :return: None
        """
        self.handler_to_process_queue.put(self.kill_signal)
        self.handler_to_process_queue = None
        while True:
            msg = self.to_handler_queue.get()
            if isinstance(msg, self.finished_signal.__class__):
                if msg == self.finished_signal:
                    break
        self._shh_no_more_tears(self.handled_process, self.to_handler_queue)

    @classmethod
    def _shh_no_more_tears(cls, process, queue_process_populates):
        """
        Close process without queue signal for cleanup.

        :rtype: None
        :return: None
        """
        if process.is_alive():
            process.terminate()
            clear_and_close_queues(queue_process_populates)
            process.join()


class PoolProcessHandler(Thread):
    """Manages pool'd asynchronous processes."""
    def __init__(self, run_target, return_queue, pool_args, *, pool_size=4, time_limit=15):
        """
        Set runtime attributes for a pooled multiprocessing application.

        :Parameters:
            :param function run_target: function / method to be run asynchronously - called once per pool_arg.
            :param queue.Queue return_queue: queue to return the results of run_target(s).
            :param list pool_args: list of objects to be mapped to run_target instances.
            :param int or None pool_size: number of sub-processes to be mapped to run_target.
            :param int or None time_limit: amount of time to await the results of run_target.
        :rtype: None
        :return: None
        """
        Thread.__init__(self)
        self.run_target = run_target
        self.return_queue = return_queue
        self.pool_args = pool_args
        self.time_limit = time_limit
        self.pool_size = pool_size

    def run(self):
        """
        Start pool'd process and return results using queue from __init__.

        :rtype: None
        :return: None
        """
        with Pool(self.pool_size) as pool:
            result = pool.map_async(self.run_target, self.pool_args)
            try:
                results_list = result.get(timeout=self.time_limit)
            except TimesUpPencilsDown:
                results_list = None
        self.return_queue.put(results_list)
