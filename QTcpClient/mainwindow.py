import os
import sys

from PySide2.QtCore import QDataStream, QByteArray, QFile, QStandardPaths, QIODevice, QFileInfo, SIGNAL, Signal
from PySide2.QtNetwork import QTcpSocket, QHostAddress, QAbstractSocket, QTcpServer
from PySide2.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QStatusBar, QTextBrowser, QHBoxLayout, QLineEdit, \
    QPushButton, QMessageBox, QFileDialog, QApplication


class MainWindow(QMainWindow):
    new_message = Signal(bytes)

    def __init__(self):
        super().__init__()
        self.socket = QTcpSocket(self)
        # layout
        self.setWindowTitle("QTCPClient")
        self._central_widget = QWidget()
        self._main_layout = QVBoxLayout()
        self.status_bar = QStatusBar()
        self.text_browser_received_messages = QTextBrowser()
        self._controller_layout = QHBoxLayout()
        self.line_edit_message = QLineEdit()
        self._controller_layout.addWidget(self.line_edit_message)
        self._buttons_layout = QHBoxLayout()
        self.send_message_button = QPushButton("Send Message")
        self.send_message_button.clicked.connect(self.on_send_message_button_clicked)
        self.send_attachment_button = QPushButton("Send Attachment")
        self.send_attachment_button.clicked.connect(self.on_send_attachment_button_clicked)
        self._buttons_layout.addWidget(self.send_message_button)
        self._buttons_layout.addWidget(self.send_attachment_button)
        # end layout

        self.new_message.connect(self.display_message)
        self.socket.readyRead.connect(self.read_socket)
        self.socket.disconnected.connect(self.discard_socket)
        self.socket.errorOccurred.connect(self.display_error)

        # set layout
        self.setStatusBar(self.status_bar)
        self.setCentralWidget(self._central_widget)
        self._central_widget.setLayout(self._main_layout)
        self._main_layout.addWidget(self.text_browser_received_messages)
        self._main_layout.addLayout(self._controller_layout)
        self._main_layout.addLayout(self._buttons_layout)

        self.socket.connectToHost(QHostAddress.LocalHost, 8080)

        if self.socket.waitForConnected():
            self.status_bar.showMessage("Connected to Server")
        else:
            QMessageBox.critical(self, "QTCPClient", f"The following error occurred: {self.socket.errorString()}.")
            if self.socket.isOpen():
                self.socket.close()
            QApplication.quit()

    def discard_socket(self):
        self.socket.deleteLater()
        self.socket = None
        self.status_bar.showMessage("Disconnected!")

    def read_socket(self):
        buffer = QByteArray()

        socket_stream = QDataStream(self.socket)
        socket_stream.setVersion(QDataStream.Qt_5_15)

        socket_stream.startTransaction()
        socket_stream >> buffer

        descriptor = self.socket.socketDescriptor()

        if not socket_stream.commitTransaction():
            message = f"{descriptor} :: Waiting for more data to come.."
            self.new_message.emit(message)
            return

        header = buffer.mid(0, 128)
        file_type = header.split(",")[0].split(":")[1]

        buffer = buffer.mid(128)

        if file_type == "attachment":
            file_name = str(header.split(",")[1].split(":")[1], "utf-8")
            ext = file_name.split(".")[1]
            size = str(header.split(",")[2].split(":")[1].split(";")[0], "utf-8")

            if QMessageBox.Yes == QMessageBox.question(self, "QTCPServer", f"You are receiving an attachment from sd:{descriptor} of size: {size} bytes, called {file_name}. Do you want to accept it?"):
                location = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation).replace(os.sep, '/') + "/"
                file_path = QFileDialog.getSaveFileName(self, "Save File", location + file_name, f"File (*.{ext})")[0]

                file = QFile(file_path)
                if file.open(QIODevice.WriteOnly):
                    file.write(buffer)
                    message = f"INFO :: Attachment from sd:{descriptor} successfully stored on disk under the path {file_path}"
                    self.new_message.emit(message)
                else:
                    QMessageBox.critical(self, "QTCPServer", "An error occurred while trying to write the attachment.")
            else:
                message = f"INFO :: Attachment from sd:{descriptor} discarded"
                self.new_message.emit(message)
        elif file_type == "descriptor":
            self.id = socket_stream.readInt32()
            self.setWindowTitle(f"QTCPClient - {self.id}")
        elif file_type == "message":
            message = f"{descriptor} :: {str(buffer, 'utf-8')}"
            self.new_message.emit(message)

    def display_error(self, socket_error: QAbstractSocket.SocketError):
        if socket_error == QAbstractSocket.RemoteHostClosedError:
            return
        elif socket_error == QAbstractSocket.HostNotFoundError:
            QMessageBox.information(self, "QTCPServer", "The host was not found. Please check the host name and port settings.")
            return
        elif socket_error == QAbstractSocket.ConnectionRefusedError:
            QMessageBox.information(self, "QTCPServer", "The connection was refused by the peer. Make sure QTCPServer is running, and check that the host name and port settings are correct.")
            return
        else:
            socket: QTcpSocket = self.sender()
            QMessageBox.information(self, "QTCPServer", f"The following error occurred: {socket.errorString()}.")
        return

    def on_send_message_button_clicked(self):
        if not self.socket:
            QMessageBox.critical(self, "QTCPServer", "Not connected")
            return

        if not self.socket.isOpen():
            QMessageBox.critical(self, "QTCPServer", "Socket doesn't seem to be opened")
            return

        string = self.line_edit_message.text()
        socket_stream = QDataStream(self.socket)
        socket_stream.setVersion(QDataStream.Qt_5_15)
        header = QByteArray()
        string_size = len(string.encode("utf-8"))
        fstring = f"fileType:message,fileName:null,fileSize:{string_size},"
        header.prepend(fstring.encode("utf-8"))
        header.resize(128)

        byte_array = QByteArray(string.encode("utf-8"))
        byte_array.prepend(header)

        socket_stream << byte_array

        self.line_edit_message.clear()

    def on_send_attachment_button_clicked(self):
        if not self.socket:
            QMessageBox.critical(self, "QTCPServer", "Not connected")
            return

        if not self.socket.isOpen():
            QMessageBox.critical(self, "QTCPServer", "Socket doesn't seem to be opened")
            return

        file_path: str = QFileDialog.getOpenFileName(self, "Select an attachment", QStandardPaths.writableLocation(QStandardPaths.DownloadLocation),"File (*.json *.txt *.png *.jpg *.jpeg)")[0]

        if not file_path:
            QMessageBox.critical(self, "QTCPClient", "You haven't selected any attachment!")
            return

        file = QFile(file_path)
        if file.open(QIODevice.ReadOnly):
            file_info = QFileInfo(file.fileName())
            file_name = file_info.fileName()

            socket_stream = QDataStream(self.socket)
            socket_stream.setVersion(QDataStream.Qt_5_15)

            header = QByteArray()
            header.prepend(f"fileType:attachment,fileName:{file_name},fileSize:{file.size()},".encode("utf-8"))
            header.resize(128)

            byte_array = file.readAll()
            byte_array.prepend(header)

            socket_stream.setVersion(QDataStream.Qt_5_15)
            socket_stream << byte_array
        else:
            QMessageBox.critical(self, "QTCPClient", "Couldn't open the attachment!")

    def display_message(self, string: str):
        self.text_browser_received_messages.append(string)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
