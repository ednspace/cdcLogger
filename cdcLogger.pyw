"""
A PyQt program using PyQWT to produce a realtime graph of CDC counts collected
from a symCDC electronics hardware package.

Data is collected at 57600 baud via RS232 from an AD7745 capacitive to
digital converter chip. The data is read from the chip via I2C with a
microcontroller and sent out to the serial port through an FTDI serial to USB chip.

Many Thanks go to Eli Bendersky for providing a starting point for this code
http://eli.thegreenplace.net/2009/08/07/a-live-data-monitor-with-python-pyqt-and-pyserial/

For more information on the electronics package and various instruments that incorporate it please visit:
http://symcdc.com/

This code updated and maintained by
Eric Daine (ednspace@gmail.com)
Last modified: 10.20.2012
"""
import random, sys
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import PyQt4.Qwt5 as Qwt
import Queue
import csv
import datetime
import time


from com_monitor import ComMonitorThread
from eblib.serialutils import full_port_name, enumerate_serial_ports
from eblib.utils import get_all_from_queue, get_item_from_queue
from livedatafeed import LiveDataFeed


class PlottingDataMonitor(QMainWindow):
    def __init__(self, parent=None):
        super(PlottingDataMonitor, self).__init__(parent)

        self.monitor_active = False
        self.logger_active = False
        self.com_monitor = None
        self.com_data_q = None
        self.com_error_q = None
        self.livefeed = LiveDataFeed()
        self.temperature_samples = []
        self.timer = QTimer()

        self.create_menu()
        self.create_main_frame()
        self.create_status_bar()

    def make_data_box(self, name):
        label = QLabel(name)
        qle = QLineEdit()
        qle.setEnabled(False)
        qle.setFrame(False)
        return (label, qle)

    def create_plot(self):
        plot = Qwt.QwtPlot(self)
        plot.setCanvasBackground(Qt.black)
        plot.setAxisTitle(Qwt.QwtPlot.xBottom, 'Time')
        plot.setAxisScale(Qwt.QwtPlot.xBottom, 0, 10, 1)
        plot.setAxisTitle(Qwt.QwtPlot.yLeft, 'CDC Counts')
        #plot.setAxisScale(Qwt.QwtPlot.yLeft, 0, 8000000, 1000000)
        plot.replot()

        curve = Qwt.QwtPlotCurve('')
        curve.setRenderHint(Qwt.QwtPlotItem.RenderAntialiased)
        pen = QPen(QColor('limegreen'))
        pen.setWidth(2)
        curve.setPen(pen)
        curve.attach(plot)

        return plot, curve

    def create_status_bar(self):
        self.status_text = QLabel('Monitor idle')
        self.statusBar().addWidget(self.status_text, 1)

    def create_main_frame(self):

        # Edit Box
        #
        self.editbox = QTextEdit()
        self.editbox.setReadOnly(True)
        editbox_layout = QVBoxLayout()
        editbox_layout.addWidget(self.editbox)
        editbox_layout.addStretch(1)
        editbox_groupbox = QGroupBox('CDC Counts')
        editbox_groupbox.setLayout(editbox_layout)


        # Port name
        #
        portname_l, self.portname = self.make_data_box('COM Port:')
        portname_layout = QHBoxLayout()
        portname_layout.addWidget(portname_l)
        portname_layout.addWidget(self.portname, 0)
        portname_layout.addStretch(1)
        portname_groupbox = QGroupBox('COM Port')
        portname_groupbox.setLayout(portname_layout)


        # Plot
        #
        self.plot, self.curve = self.create_plot()
        plot_layout = QVBoxLayout()
        plot_layout.addWidget(self.plot)
        plot_groupbox = QGroupBox('Capacitive to Digital Sensor Graph')
        plot_groupbox.setLayout(plot_layout)



        # Main frame and layout
        #
        self.main_frame = QWidget()
        main_layout = QVBoxLayout()
        main_layout.addWidget(portname_groupbox)
        main_layout.addWidget(plot_groupbox)
        main_layout.addWidget(editbox_groupbox)
        main_layout.addStretch(1)
        self.main_frame.setLayout(main_layout)

        self.setCentralWidget(self.main_frame)
        self.set_actions_enable_state()

    def create_menu(self):
        self.file_menu = self.menuBar().addMenu("&File")

        selectport_action = self.create_action("Select COM &Port...",
            shortcut="Ctrl+P", slot=self.on_select_port, tip="Select a COM port")
        self.startMon_action = self.create_action("&Start monitor",
            shortcut="Ctrl+M", slot=self.on_startMon, tip="Start the data monitor")
        self.stopMon_action = self.create_action("&Stop monitor",
            shortcut="Ctrl+T", slot=self.on_stopMon, tip="Stop the data monitor")

        self.startLog_action = self.create_action("&Start logger",
            shortcut="Ctrl+L", slot=self.on_startLog, tip="Start the data logger")
        self.stopLog_action = self.create_action("&Stop logger",
            shortcut="Ctrl+T", slot=self.on_stopLog, tip="Stop the data logger")



        exit_action = self.create_action("E&xit", slot=self.close,
            shortcut="Ctrl+X", tip="Exit the application")
        self.startMon_action.setEnabled(False)
        self.stopMon_action.setEnabled(False)

        self.startLog_action.setEnabled(False)
        self.stopLog_action.setEnabled(False)

        self.add_actions(self.file_menu,
            (   selectport_action, self.startMon_action, self.stopMon_action, self.startLog_action, self.stopLog_action,
                None, exit_action))

        self.help_menu = self.menuBar().addMenu("&Help")
        about_action = self.create_action("&About",
            shortcut='F1', slot=self.on_about,
            tip='About the monitor')

        self.add_actions(self.help_menu, (about_action,))

    def set_actions_enable_state(self):
        if self.portname.text() == '':
            startMon_enable = stopMon_enable = False
            startLog_enable = stopLog_enable = False
        else:
            startMon_enable = not self.monitor_active
            stopMon_enable = self.monitor_active
            startLog_enable = not self.logger_active
            stopLog_enable = self.logger_active

        self.startLog_action.setEnabled(startLog_enable)
        self.startMon_action.setEnabled(startMon_enable)

        self.stopLog_action.setEnabled(stopLog_enable)
        self.stopMon_action.setEnabled(stopMon_enable)

    def on_about(self):
        msg = __doc__
        QMessageBox.about(self, "About the demo", msg.strip())

    def on_select_port(self):
        ports = list(enumerate_serial_ports())
        if len(ports) == 0:
            QMessageBox.critical(self, 'No ports',
                'No serial ports found')
            return

        item, ok = QInputDialog.getItem(self, 'Select a port',
                    'Serial port:', ports, 0, False)

        if ok and not item.isEmpty():
            self.portname.setText(item)
            self.set_actions_enable_state()

    def on_stopMon(self):
        """ Stop the monitor
        """
        if self.com_monitor is not None:
            self.com_monitor.join(10)
            self.com_monitor = None

        self.monitor_active = False
        self.timer.stop()
        self.set_actions_enable_state()
        self.status_text.setText('Monitor idle')


    def on_startMon(self):
        """ Start the monitor: com_monitor thread and the update timer
        """
        if self.com_monitor is not None or self.portname.text() == '':
            return

        self.data_q = Queue.Queue()
        self.error_q = Queue.Queue()
        self.com_monitor = ComMonitorThread(
            self.data_q,
            self.error_q,
            full_port_name(str(self.portname.text())),
            57600)
        self.com_monitor.start()

        com_error = get_item_from_queue(self.error_q)
        if com_error is not None:
            QMessageBox.critical(self, 'ComMonitorThread error', com_error)
            self.com_monitor = None

        self.monitor_active = True
        #self.logger_active = True
        self.set_actions_enable_state()

        self.timer = QTimer()
        self.connect(self.timer, SIGNAL('timeout()'), self.on_timer)

        self.timer.start(.005)
        self.status_text.setText('Monitor running')

        #update_freq = self.updatespeed_knob.value()
        #if update_freq > 0:
        #   self.timer.start(100.0 / update_freq)

    def on_startLog(self):
        self.log()
        self.logger_active = True
        self.set_actions_enable_state()

    def on_stopLog(self):
        self.logger_active = False
        self.set_actions_enable_state()

    def on_timer(self):
        """ Executed periodically when the monitor update timer
            is fired.
        """
        self.read_serial_data()
        self.update_monitor()

    def log(self):
        self.log_state = True
        self.reading_num = 0

        self.today = str(datetime.date.today())
        self.logname = '%s.csv' % self.today
        self.file = csv.writer(open(self.logname, "wb"))

    def save_data(self,reading):
        self.file.writerow ([reading])

    def save_data_stamps(self,reading_num,reading,timestamp,utimestamp):
        self.file.writerow ([reading_num,reading,timestamp,utimestamp])

    def update_monitor(self):
        """ Updates the state of the monitor window with new
            data. The livefeed is used to find out whether new
            data was received since the last update. If not,
            nothing is updated.
        """
        if self.livefeed.has_new_data:
            data = self.livefeed.read_data()


            self.temperature_samples.append(
                (data['timestamp'], data['temperature']))
            if len(self.temperature_samples) > 500:
                self.temperature_samples.pop(0)

            xdata = [s[0] for s in self.temperature_samples]
            ydata = [s[1] for s in self.temperature_samples]

            #avg = sum(ydata) / float(len(ydata))

            self.plot.setAxisScale(Qwt.QwtPlot.xBottom, xdata[0], max(20, xdata[-1]))
            self.curve.setData(xdata, ydata)
            self.plot.replot()

            #self.thermo.setValue(avg)

    def read_serial_data(self):
        """ Called periodically by the update timer to read data
            from the serial port.
        """
        qdata = list(get_all_from_queue(self.data_q))
        if len(qdata) > 0: #At this point qdata object is a list type
            count = 0
            for elem in list(qdata):
                self.editbox.append(qdata[count][0])
                if self.editbox.document().blockCount() == 4096:
                    self.editbox.clear()
                data = dict(timestamp=qdata[count][1],temperature=int(qdata[count][0]))
                self.livefeed.add_data(data)


                if self.logger_active:
                    self.reading_num = self.reading_num + 1
                    utimestamp = time.time() #A unix style timestamp for the log

                    #Uncomment for stamps
                    #self.save_data_stamps(self.reading_num,int(qdata[count][0]),qdata[count][1],utimestamp)

                    self.save_data(int(qdata[count][0]))

                count=count+1

            #data = dict(timestamp=qdata[-1][1],
            #           temperature=int(qdata[-1][0]))

            #self.livefeed.add_data(data)

    # The following two methods are utilities for simpler creation
    # and assignment of actions
    #
    def add_actions(self, target, actions):
        for action in actions:
            if action is None:
                target.addSeparator()
            else:
                target.addAction(action)

    def create_action(  self, text, slot=None, shortcut=None,
                        icon=None, tip=None, checkable=False,
                        signal="triggered()"):
        action = QAction(text, self)
        if icon is not None:
            action.setIcon(QIcon(":/%s.png" % icon))
        if shortcut is not None:
            action.setShortcut(shortcut)
        if tip is not None:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            self.connect(action, SIGNAL(signal), slot)
        if checkable:
            action.setCheckable(True)
        return action

    def closeEvent(self, event):
        self.editbox.append("closing PyQtTest")



def main():
    app = QApplication(sys.argv)
    form = PlottingDataMonitor()
    form.show()
    app.exec_()


if __name__ == "__main__":
    main()



