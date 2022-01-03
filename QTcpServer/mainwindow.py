import sys
from typing import List

from PySide2.QtCore import Signal, QByteArray, QDataStream, QStandardPaths, QFile, QIODevice, QFileInfo
from PySide2.QtNetwork import QTcpServer, QHostAddress, QTcpSocket, QAbstractSocket
from PySide2.QtWidgets import QMainWindow, QMessageBox, QStatusBar, QHBoxLayout, QWidget, QPushButton, QVBoxLayout, \
    QTextBrowser, QComboBox, QLineEdit, QFileDialog, QApplication


class MainWindow(QMainWindow):
    new_message = Signal(str)
    _connection_set: List[QTcpSocket] = []

    def __init__(self):
        super().__init__()
        self.server = QTcpServer()

        # layout
        self.setWindowTitle("QTCPServer")
        self._central_widget = QWidget()
        self._main_layout = QVBoxLayout()
        self.status_bar = QStatusBar()
        self.text_browser_received_messages = QTextBrowser()
        self._controller_layout = QHBoxLayout()
        self.combobox_receiver = QComboBox()
        self.combobox_receiver.insertItem(-1, "Broadcast")
        self.line_edit_message = QLineEdit()
        self._controller_layout.addWidget(self.combobox_receiver)
        self._controller_layout.addWidget(self.line_edit_message)
        self._buttons_layout = QHBoxLayout()
        self.send_message_button = QPushButton("Send Message")
        self.send_message_button.clicked.connect(self.send_message_button_clicked)
        self.send_attachment_button = QPushButton("Send Attachment")
        self.send_attachment_button.clicked.connect(self.send_attachment_button_clicked)
        self._buttons_layout.addWidget(self.send_message_button)
        self._buttons_layout.addWidget(self.send_attachment_button)
        # end layout

        if self.server.listen(QHostAddress.Any, 8080):
            self.new_message.connect(self.display_message)
            self.server.newConnection.connect(self.new_connection)
            self.status_bar.showMessage("Server is listening...")
        else:
            QMessageBox.critical(self, "QTCPServer", f"Unable to start the server: {self.server.errorString()}.")

            self.server.close()
            self.server.deleteLater()

            QApplication.quit()

        # set layout
        self.setStatusBar(self.status_bar)
        self.setCentralWidget(self._central_widget)
        self._central_widget.setLayout(self._main_layout)
        self._main_layout.addWidget(self.text_browser_received_messages)
        self._main_layout.addLayout(self._controller_layout)
        self._main_layout.addLayout(self._buttons_layout)

    def new_connection(self) -> None:
        while self.server.hasPendingConnections():
            self.append_to_socket_list(self.server.nextPendingConnection())

    def append_to_socket_list(self, socket: QTcpSocket):
        self._connection_set.insert(len(self._connection_set), socket)
        socket.readyRead.connect(self.read_socket)
        socket.disconnected.connect(self.discard_socket)
        socket.errorOccurred.connect(self.display_error)

        descriptor = socket.socketDescriptor()
        self.combobox_receiver.addItem(str(descriptor), descriptor)
        self.display_message(f"INFO :: Client with socket:{descriptor} has just entered the room")

        socket_stream = QDataStream(socket)
        fstring = f"fileType:descriptor,fileName:null,fileSize:{int(descriptor).bit_length()},"
        header = QByteArray()
        header.prepend(fstring.encode("utf-8"))
        header.resize(128)

        socket_stream << header
        socket_stream.writeInt32(int(descriptor))

    def read_socket(self):
        socket: QTcpSocket = self.sender()
        buffer = QByteArray()

        socket_stream = QDataStream(socket)
        socket_stream.setVersion(QDataStream.Qt_5_15)

        socket_stream.startTransaction()
        socket_stream >> buffer

        descriptor = socket.socketDescriptor()

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
                location = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) + "/"
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
        elif file_type == "message":
            message = f"{descriptor} :: {str(buffer, 'utf-8')}"
            self.new_message.emit(message)

    def discard_socket(self):
        socket: QTcpSocket = self.sender()

        it = self._connection_set.index(socket)

        if it is not None and it != len(self._connection_set):
            self.display_message(f"INFO :: A client has just left the room")
            del self._connection_set[it]
        socket.deleteLater()

        self.refresh_combobox()

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

    def send_message_button_clicked(self):
        receiver = self.combobox_receiver.currentText()
        if receiver == "Broadcast":
            for socket in self._connection_set:
                self.send_message(socket)
        else:
            for socket in self._connection_set:
                if socket.socketDescriptor() == int(receiver):
                    self.send_message(socket)
                    return
        self.line_edit_message.clear()

    def send_attachment_button_clicked(self):
        receiver = self.combobox_receiver
        file_path = QFileDialog.getOpenFileName(self, "Select an attachment", QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation), "File (*.json *.txt *.png *.jpg *.jpeg)")[0]
        if not file_path:
            QMessageBox.critical(self, "QTCPClient", "You haven't selected any attachment!")
            return
        if receiver.currentText() == "Broadcast":
            for socket in self._connection_set:
                self.send_attachment(socket, file_path)
        else:
            for socket in self._connection_set:
                if socket.socketDescriptor() == receiver.currentData():
                    self.send_attachment(socket, file_path)
                    return
        self.line_edit_message.clear()

    def send_message(self, socket: QTcpSocket):
        if not socket:
            QMessageBox.critical(self, "QTCPServer", "Not connected")
            return

        if not socket.isOpen():
            QMessageBox.critical(self, "QTCPServer", "Socket doesn't seem to be opened")
            return

        string = self.line_edit_message.text()
        socket_stream = QDataStream(socket)
        socket_stream.setVersion(QDataStream.Qt_5_15)
        header = QByteArray()
        string_size = len(string.encode("utf-8"))
        fstring = f"fileType:message,fileName:null,fileSize:{string_size},"
        header.prepend(fstring.encode("utf-8"))
        header.resize(128)

        byte_array = QByteArray(string.encode("utf-8"))
        byte_array.prepend(header)

        socket_stream << byte_array

    def send_attachment(self, socket: QTcpSocket, file_path: str):
        if not socket:
            QMessageBox.critical(self, "QTCPServer", "Not connected")
            return

        if not socket.isOpen():
            QMessageBox.critical(self, "QTCPServer", "Socket doesn't seem to be opened")
            return

        file = QFile(file_path)
        if file.open(QIODevice.ReadOnly):
            file_info = QFileInfo(file.fileName())
            file_name = file_info.fileName()

            socket_stream = QDataStream(socket)
            socket_stream.setVersion(QDataStream.Qt_5_15)

            header = QByteArray()
            header.prepend(f"fileType:attachment,fileName:{file_name},fileSize:{file.size()},".encode("utf-8"))
            header.resize(128)

            byte_array = file.readAll()
            byte_array.prepend(header)

            socket_stream << byte_array
        else:
            QMessageBox.critical(self, "QTCPClient", "Couldn't open the attachment!")

    def display_message(self, string):
        self.text_browser_received_messages.append(string)

    def refresh_combobox(self):
        self.combobox_receiver.clear()
        self.combobox_receiver.insertItem(-1, "Broadcast")
        for socket in self._connection_set:
            descriptor = socket.socketDescriptor()
            self.combobox_receiver.addItem(str(descriptor), descriptor)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
