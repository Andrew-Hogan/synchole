"""Basic toolkit for asynchronous task communication / management using friendly threaded queues."""
# USE EXAMPLES & TESTING TO BE COMPLETED.

from threading import Thread
from multiprocessing import Pool, Process
from multiprocessing.context import TimeoutError as TimesUpPencilsDown
from multiprocessing import Queue as MultiQueue
from queue import Queue
from queue import Empty as EmptyQueue


KILL = "CLOSE"
DONE = "DONE"
CZEC = "CHECK"


def clear_and_close_queues(*queues):
    """Close an arbitrary-length tuple of multiprocessing and queue lib queue(s)."""
    for queue in queues:
        clear_queues(queue)
        try:
            queue.close()
        except AttributeError:
            with queue.mutex:
                queue.queue.clear()


def clear_queues(*queues):
    """Remove remaining items in an arbitrary-length tuple of multiprocessing and queue lib queue(s)."""
    for queue in queues:
        try:
            while not queue.empty():
                _ = queue.get()
        except OSError:
            pass


class ProcessHost(object):
    """Multiprocessing/threading object which can be accessed directly within libraries like Tkinter."""
    def __init__(self, root, message_callback, process_target=None, *process_args,
                 message_check_delay=1000,
                 running_check_delay=10000,
                 run_process=True,
                 host_to_process_signals=None,
                 finished_signal=DONE,
                 kill_signal=KILL,
                 check_signal=CZEC,
                 **process_kwarg_dict):
        """Create private inter-process communication for a potentially newly started process."""
        self.root = root
        self.message_check_rate = message_check_delay
        self.running_check_delay = running_check_delay
        self.message_callback = message_callback
        self._to_host_queue = Queue()  # Please respect the privacy of these attributes. Altering them without
        self._to_handler_queue = MultiQueue()  # consideration for processes relying on their private state can have
        self.kill_signal = kill_signal  # unintended process opening / closing, especially with reuse.
        self.finished_signal = finished_signal
        self.check_signal = check_signal
        self._continue_running = run_process
        self._current_processor = None
        assert (self.kill_signal
                != self.finished_signal
                != self.check_signal
                != self.finished_signal), "Use unique built-in queue signals."
        self.process_end_signals = {self.kill_signal, self.finished_signal, self.check_signal}
        self.make_single_process_handler(process_target,
                                         process_args=process_args,
                                         host_to_process_signals=host_to_process_signals,
                                         process_kwarg_dict=process_kwarg_dict)

    def make_single_process_handler(self, process_target, *process_args,
                                    host_to_process_signals=None,
                                    **process_kwarg_dict):
        """Create a process handler and Tkinter threads for process callbacks."""
        _handler_to_process_queue = MultiQueue() if host_to_process_signals else None
        self._current_processor(process_target,
                                self._to_handler_queue,
                                self._to_host_queue, process_args=process_args,
                                handler_to_process_queue=_handler_to_process_queue,
                                finished_signal=self.finished_signal,
                                kill_signal=self.kill_signal,
                                check_signal=self.check_signal,
                                host_to_process_signals=host_to_process_signals,
                                process_kwarg_dict=process_kwarg_dict).start()
        self.root.after(self.message_check_rate, self.check_message)
        self.root.after(self.running_check_delay, self.check_running)

    def check_message(self, *, message_callback=None):
        """Initiate callbacks from inter-process communication."""
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
        """End current process / clear queues."""
        self._continue_running = False
        if (self._current_processor is not None
                and self._current_processor.is_alive()):
            if need_to_signal:
                self._to_handler_queue.put(self.kill_signal)
                clear_queues(self._to_host_queue)
            self._current_processor.join()
        clear_queues(self._to_host_queue, self._to_handler_queue)
        self._current_processor = None

    def check_running(self):
        """Maintain communication with subprocess to ensure it's running."""
        if (self._continue_running
                and self._current_processor is not None
                and self._current_processor.is_alive()):
            self._to_handler_queue.put(self.check_signal)
            self.root.after(self.running_check_delay, self.check_running)


class SingleProcessHandler(Thread):
    """Manages single asynchronous processes - nothing in this object should be interacted with directly."""
    def __init__(self, process_target, to_handler_queue, handler_to_host_queue, *process_args,
                 handler_to_process_queue=None,
                 finished_signal=DONE,
                 kill_signal=KILL,
                 check_signal=CZEC,
                 host_to_process_signals=None,
                 **process_kwarg_dict):
        """Set runtime attributes for multi-process communication / management."""
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
        """Create the tuple of process args needed for multiprocessing.Process."""
        if process_args and process_kwarg_dict:
            self.process_args = process_args + (process_kwarg_dict,)
        elif process_args:
            self.process_args = process_args
        elif process_kwarg_dict:
            self.process_args = (process_kwarg_dict,)

    def run(self):
        """Start / maintain process communication."""
        self.handled_process = Process(target=self.process_target,
                                       args=self.process_args)
        self.handled_process.start()
        should_run = True
        while should_run:
            should_run = self.process_queues()

    def process_queues(self):
        """Transmit / interpret signals between processes."""
        should_run = True
        msg = self.to_handler_queue.get()
        if msg in self.end_sigs:
            self.kill_process()
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
        return should_run

    def kill_process(self):
        """Handle queue / process cleanup for end-process signals."""
        if self.handled_process is not None:
            if self.handler_to_process_queue:
                self._okay_maybe_some_tears_but_be_quick()
            else:
                self._shh_no_more_tears(self.handled_process, self.to_handler_queue)
            self.handled_process = None

    def _okay_maybe_some_tears_but_be_quick(self):
        """Close process while allowing for one to-process-queue signal for cleanup."""
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
        """Close process without queue signal for cleanup."""
        if process.is_alive():
            process.terminate()
            clear_and_close_queues(queue_process_populates)
            process.join()


class PoolProcessHandler(Thread):
    """Manages pool'd asynchronous processes."""
    def __init__(self, run_target, return_queue, pool_args, *, pool_size=4, time_limit=15):
        """Set runtime attributes for a pooled multiprocessing application."""
        Thread.__init__(self)
        self.run_target = run_target
        self.return_queue = return_queue
        self.pool_args = pool_args
        self.time_limit = time_limit
        self.pool_size = pool_size

    def run(self):
        """Start pool'd process and return results using queue from __init__."""
        with Pool(self.pool_size) as pool:
            result = pool.map_async(self.run_target, self.pool_args)
            try:
                results_list = result.get(timeout=self.time_limit)
            except TimesUpPencilsDown:
                results_list = None
        self.return_queue.put(results_list)
