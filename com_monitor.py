import Queue
import threading
import time
import datetime
import serial


class ComMonitorThread(threading.Thread):
    """ A thread for monitoring a COM port. The COM port is
        opened when the thread is started.

        data_q:
            Queue for received data. Items in the queue are
            (data, timestamp) pairs, where data is a binary
            string representing the received data, and timestamp
            is the time elapsed from the thread's start (in
            seconds).

        error_q:
            Queue for error messages. In particular, if the
            serial port fails to open for some reason, an error
            is placed into this queue.

        port:
            The COM port to open. Must be recognized by the
            system.

        port_baud/stopbits/parity:
            Serial communication parameters

        port_timeout:
            The timeout used for reading the COM port. If this
            value is low, the thread will return data in finer
            grained chunks, with more accurate timestamps, but
            it will also consume more CPU.
    """
    def __init__(   self,
                    data_q, error_q,
                    port_num,
                    port_baud,
                    port_stopbits=serial.STOPBITS_ONE,
                    port_parity=serial.PARITY_NONE,
                    #port_timeout=0.01 //Changed this so incoming data wasn't interrupted
                    port_timeout=1):
        threading.Thread.__init__(self)

        self.serial_port = None
        self.serial_arg = dict( port=port_num,
                                baudrate=port_baud,
                                stopbits=port_stopbits,
                                parity=port_parity,
                                timeout=port_timeout)

        self.data_q = data_q
        self.error_q = error_q

        self.alive = threading.Event()
        self.alive.set()

    def run(self):
        try:
            if self.serial_port:
                self.serial_port.close()
            self.serial_port = serial.Serial(**self.serial_arg)
        except serial.SerialException, e:
            self.error_q.put(e.message)
            return

        #Setup log File and Restart the Chip

        self.reset()

        # Restart the clock
        time.clock()

        while self.alive.isSet():

            data = self.serial_port.readline()
            data=data.strip("\n \r")

            if len(data) > 0:
                timestamp = time.clock() #A seconds elapsed style time stamp for the plot
                self.data_q.put((data, timestamp))

        #clean up
        if self.serial_port:
            self.serial_port.close()







    def reset(self):
        self.serial_port.write("r\n\r") #restart the AD7745 chip
        time.sleep(3)
        self.serial_port.write("m\n\r") #Start streaming back CDC counts
        time.sleep(1)

        #Clear the Port
        self.serial_port.flushInput()



    def join(self, timeout=None):
        self.alive.clear()
        threading.Thread.join(self, timeout)

