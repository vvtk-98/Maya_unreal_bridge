import maya.cmds as cmds
import os
import maya.utils
import time
import threading
import socket
import json
import traceback


class MayaUnrealSocketBridge:
    def __init__(self, host="127.0.0.1", port=12112):
        self.host = host
        self.port = port
        self.buffer_size = 4096
        self.socket_server = None
        self.client_socket = None
        self.server_thread = None
        self.is_running = False
        self.connected_clients = []

    def start_server(self):
        if self.is_running:
            print("Socket server is already running")
            return

        try:
            import socket
            import threading
        except ImportError as e:
            print(f"Failed to import required modules: {str(e)}")
            return False

        try:
            self.socket_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket_server.bind((self.host, self.port))
            self.socket_server.listen(5)
            self.is_running = True

            print(f"Maya socket server started on {self.host}:{self.port}")

            self.server_thread = threading.Thread(target=self.accept_connections)
            self.server_thread.daemon = True
            self.server_thread.start()

            return True
        except Exception as e:
            print(f"Failed to start socket server: {str(e)}")
            return False

    def accept_connections(self):
        import threading
        try:
            import socket
        except ImportError as e:
            print(f"Failed to import 'socket' module: {str(e)}")
            return

        self.socket_server.settimeout(1.0)

        while self.is_running:
            try:
                client_socket, address = self.socket_server.accept()
                print(f"Connection established with {address}")
                self.connected_clients.append(client_socket)
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket,))
                client_thread.daemon = True
                client_thread.start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.is_running:
                    print(f"Error accepting connection: {str(e)}")

    def handle_client(self, client_socket):
        try:
            import json
        except ImportError as e:
            print(f"Failed to import 'json' module: {str(e)}")
            return
        try:
            while self.is_running:
                data = client_socket.recv(self.buffer_size)
                if not data:
                    break

                message = data.decode('utf-8')
                print(f"Received from Unreal: {message}")

                self.process_message(message, client_socket)

        except Exception as e:
            print(f"Error handling client: {str(e)}")
        finally:
            if client_socket in self.connected_clients:
                self.connected_clients.remove(client_socket)
            client_socket.close()

    def process_message(self, message, client_socket):
        try:
            import json
        except ImportError as e:
            print(f"Failed to import 'json' module: {str(e)}")
            return
        try:
            data = json.loads(message)
            command = data.get('command')
            command_id = data.get('id')
            if command == 'ping':
                self.send_response(client_socket, {'status': 'ok', 'message': 'pong', 'id': command_id})
            elif command == 'get_selection':
                try:
                    def get_selection_in_main_thread():
                        try:
                            selected = cmds.ls(selection=True)
                            print(f"Selected objects: {selected}")
                            return selected
                        except Exception as e:
                            print(f"Error in get_selection_in_main_thread: {str(e)}")
                            return []

                    selected = maya.utils.executeInMainThreadWithResult(get_selection_in_main_thread)
                    long_selected = []
                    for obj in selected:
                        try:
                            long_name = cmds.ls(obj, long=True)
                            if long_name:
                                long_selected.append(long_name[0])
                            else:
                                long_selected.append(obj)
                        except:
                            long_selected.append(obj)
                    self.send_response(client_socket, {
                        'status': 'ok',
                        'selection': long_selected,
                        'id': command_id
                    })
                except Exception as sel_error:
                    print(f"Error getting selection: {str(sel_error)}")
                    self.send_response(client_socket, {
                        'status': 'error',
                        'message': f"Could not get selection: {str(sel_error)}",
                        'id': command_id
                    })
            elif command == 'get_transform':
                obj_name = data.get('object')
                if obj_name and cmds.objExists(obj_name):
                    translation = cmds.xform(obj_name, query=True, worldSpace=True, translation=True)
                    rotation = cmds.xform(obj_name, query=True, worldSpace=True, rotation=True)
                    scale = cmds.xform(obj_name, query=True, worldSpace=True, scale=True)

                    self.send_response(client_socket, {
                        'status': 'ok',
                        'transform': {
                            'translation': translation,
                            'rotation': rotation,
                            'scale': scale
                        },
                        'id': command_id
                    })
                else:
                    self.send_response(client_socket, {
                        'status': 'error',
                        'message': f"Object '{obj_name}' not found",
                        'id': command_id
                    })

            else:
                self.send_response(client_socket, {
                    'status': 'error',
                    'message': f"Unknown command: {command}",
                    'id': command_id
                })

        except json.JSONDecodeError:
            self.send_response(client_socket, {
                'status': 'error',
                'message': 'Invalid JSON format'
            })
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error processing message: {str(e)}")
            print(f"Error details: {error_details}")
            self.send_response(client_socket, {
                'status': 'error',
                'message': str(e)
            })

    def send_response(self, client_socket, data):
        try:
            import json
        except ImportError as e:
            print(f"Failed to import 'json' module: {str(e)}")
            return

        try:
            response = json.dumps(data)
            client_socket.sendall(response.encode('utf-8'))
        except Exception as e:
            print(f"Error sending response: {str(e)}")

    def broadcast_to_clients(self, data):
        try:
            import json
        except ImportError as e:
            print(f"Failed to import 'json' module: {str(e)}")
            return

        message = json.dumps(data)
        disconnected_clients = []

        for client in self.connected_clients:
            try:
                client.sendall(message.encode('utf-8'))
            except:
                disconnected_clients.append(client)

        for client in disconnected_clients:
            if client in self.connected_clients:
                self.connected_clients.remove(client)

    def stop_server(self):
        self.is_running = False

        for client in self.connected_clients:
            try:
                client.close()
            except:
                pass
        self.connected_clients = []

        if self.socket_server:
            try:
                self.socket_server.close()
            except:
                pass
            self.socket_server = None

        print("Socket server stopped")


class SocketBridgeUI:
    def __init__(self, bridge):
        self.bridge = bridge
        self.selected_objects = []
        self.default_export_path = r"export_path_save_assets"
        self.progress_control = None
        self.cancel_export = False
        self.window_name = "mayaUnrealSocketBridge"
        self.export_frame = None

        if not os.path.exists(self.default_export_path):
            os.makedirs(self.default_export_path)

    def on_window_close(self, *args):
        print("Socket Bridge UI window closed, stopping socket server...")
        self.bridge.stop_server()

    def update_progress(self, value):
        if self.progress_control and cmds.progressBar(self.progress_control, exists=True):
            cmds.progressBar(
                self.progress_control,
                edit=True,
                progress=value
            )
            cmds.refresh()

    def show_progress_bar(self, show=True):
        if self.progress_control:
            cmds.progressBar(self.progress_control, edit=True, visible=show)
        if self.cancel_btn:
            cmds.button(self.cancel_btn, edit=True, visible=show)

    def cancel_export_process(self):
        self.cancel_export = True
        cmds.button(self.export_btn, edit=True, enable=True)
        self.show_progress_bar(False)

    def create_ui(self):
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)

        window = cmds.window(
            self.window_name,
            title="Maya-Unreal Live Link",
            widthHeight=(450, 600),
            sizeable=True,
            closeCommand=self.on_window_close
        )

        main_layout = cmds.scrollLayout(width=450, height=600)
        form_layout = cmds.formLayout(parent=main_layout)

        title_text = cmds.text(
            label="Maya-Unreal Live Link",
            font="boldLabelFont",
            parent=form_layout
        )

        objects_frame = cmds.frameLayout(
            label="Assets selected to Export",
            collapsable=True,
            width=430,
            height=200,
            parent=form_layout
        )

        self.selected_list = cmds.textScrollList(
            numberOfRows=10,
            allowMultiSelection=False,
            append=self.get_selected_objects(),
            selectCommand=self.on_selection_changed,
            width=420,
            height=180,
            parent=objects_frame
        )

        cmds.popupMenu(parent=self.selected_list)
        cmds.menuItem(label="Refresh List", command=lambda x: self.refresh_selected_objects())
        cmds.menuItem(label="Clear Selection", command=lambda x: self.clear_selection())
        cmds.setParent('..')

        server_frame = cmds.frameLayout(
            label="Live Link Controls",
            collapsable=True,
            width=430,
            height=100,
            parent=form_layout
        )

        self.connect_btn = cmds.button(
            label="Establish Connection",
            command=lambda x: self.start_server_and_refresh(),
            height=30,
            width=200,
            backgroundColor=(0.8, 1.0, 0.8),
            parent=server_frame
        )

        self.disconnect_btn = cmds.button(
            label="Disconnect",
            command=lambda x: self.bridge.stop_server(),
            height=30,
            width=200,
            backgroundColor=(1.0, 0.8, 0.8),
            parent=server_frame
        )

        cmds.setParent('..')

        self.export_frame = cmds.frameLayout(
            label="Export Controls",
            collapsable=True,
            width=430,
            height=120,
            parent=form_layout
        )

        export_col_layout = cmds.columnLayout(
            adjustableColumn=True,
            rowSpacing=5,
            parent=self.export_frame
        )

        self.export_btn = cmds.button(
            label="Export to Unreal",
            command=lambda x: self.export_alembic_to_unreal(),
            height=30,
            width=420,
            parent=export_col_layout
        )

        self.cancel_btn = cmds.button(
            label="Cancel Export",
            command=lambda x: self.cancel_export_process(),
            height=30,
            width=420,
            visible=False,
            parent=export_col_layout
        )

        self.progress_control = cmds.progressBar(
            width=420,
            height=25,
            minValue=0,
            maxValue=100,
            visible=False,
            parent=export_col_layout
        )

        cmds.setParent('..')
        cmds.setParent('..')

        status_text = cmds.text(
            label=f"Server Address: {self.bridge.host}:{self.bridge.port}",
            align="left",
            parent=form_layout
        )

        cmds.formLayout(
            form_layout,
            edit=True,
            attachForm=[
                (title_text, 'top', 5),
                (title_text, 'left', 5),
                (objects_frame, 'top', 30),
                (objects_frame, 'left', 5),
                (server_frame, 'top', 240),
                (server_frame, 'left', 5),
                (self.export_frame, 'top', 350),
                (self.export_frame, 'left', 5),
                (status_text, 'bottom', 5),
                (status_text, 'left', 5)
            ],
            attachControl=[
                (server_frame, 'top', 5, objects_frame),
                (self.export_frame, 'top', 5, server_frame)
            ]
        )

        self.refresh_selected_objects()
        cmds.showWindow(window)

    def get_selected_objects(self):
        """Get currently selected objects in Maya"""
        self.selected_objects = cmds.ls(selection=True, long=True) or []
        return self.selected_objects

    def refresh_selected_objects(self):
        """Refresh the list of selected objects in the UI"""
        selected = self.get_selected_objects()
        cmds.textScrollList(self.selected_list, edit=True, removeAll=True)
        cmds.textScrollList(self.selected_list, edit=True, append=selected)

    def clear_selection(self):
        """Clear the current selection in Maya and UI"""
        cmds.select(clear=True)
        self.refresh_selected_objects()

    def on_selection_changed(self):
        """When user selects an item in the UI list, select it in Maya"""
        selected_item = cmds.textScrollList(self.selected_list, query=True, selectItem=True)
        if selected_item:
            cmds.select(selected_item, replace=True)

    def start_server_and_refresh(self):
        """Start server and refresh the UI"""
        if self.bridge.start_server():
            self.refresh_selected_objects()

    def export_alembic_to_unreal(self, export_path=None):
        selected = cmds.ls(selection=True)
        if not selected:
            cmds.warning("No objects selected for Alembic export")
            return False

        self.show_progress_bar(True)
        cmds.button(self.export_btn, edit=True, enable=False)
        cmds.button(self.cancel_btn, edit=True, enable=True, visible=True)
        self.cancel_export = False

        self.update_progress(0)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        default_filename = f"export_{timestamp}.abc"
        export_path = os.path.join(self.default_export_path, default_filename)

        export_thread = threading.Thread(
            target=self._perform_alembic_export,
            args=(selected, export_path)
        )
        export_thread.start()

        return True

    def _perform_alembic_export(self, selected, export_path):
        try:
            maya.utils.executeInMainThreadWithResult(
                lambda: self.update_progress(10)
            )

            result = maya.utils.executeInMainThreadWithResult(
                lambda: cmds.confirmDialog(
                    title='Material Import Method',
                    message='How should Unreal handle materials during import?',
                    button=['Find existing Materials', 'Create new Materials', 'Cancel'],
                    defaultButton='Find Existing Materials',
                    cancelButton='Cancel',
                    dismissString='Cancel'
                )
            )

            if result == 'Cancel' or self.cancel_export:
                maya.utils.executeInMainThreadWithResult(
                    lambda: cmds.warning("Alembic export cancelled")
                )
                maya.utils.executeInMainThreadWithResult(
                    lambda: [
                        cmds.button(self.export_btn, edit=True, enable=True),
                        self.show_progress_bar(False)
                    ]
                )
                return False

            material_import_method = 'find' if result == 'Find existing Materials' else 'create'

            start_frame = maya.utils.executeInMainThreadWithResult(
                lambda: cmds.playbackOptions(query=True, minTime=True)
            )
            end_frame = maya.utils.executeInMainThreadWithResult(
                lambda: cmds.playbackOptions(query=True, maxTime=True)
            )

            maya.utils.executeInMainThreadWithResult(
                lambda: self.update_progress(30)
            )

            abc_params = "-frameRange {0} {1} ".format(start_frame, end_frame)
            abc_params += "-attr motionVectorColorSet "
            abc_params += "-stripNamespaces "
            abc_params += "-uvWrite "
            abc_params += "-writeColorSets "
            abc_params += "-writeFaceSets "
            abc_params += "-worldSpace "
            abc_params += "-writeUVSets "
            abc_params += "-dataFormat ogawa "

            maya.utils.executeInMainThreadWithResult(
                lambda: self.update_progress(50)
            )

            export_command = f"{abc_params} -root {' -root '.join(selected)} -file {export_path}"
            maya.utils.executeInMainThreadWithResult(
                lambda: cmds.AbcExport(j=export_command)
            )

            maya.utils.executeInMainThreadWithResult(
                lambda: self.update_progress(80)
            )

            data = {
                'command': 'import_alembic',
                'file_path': export_path,
                'objects': selected,
                'material_import_method': material_import_method
            }
            self.bridge.broadcast_to_clients(data)

            maya.utils.executeInMainThreadWithResult(
                lambda: self.update_progress(100)
            )

            maya.utils.executeInMainThreadWithResult(
                lambda: print(f"Alembic exported successfully to: {export_path}")
            )

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            maya.utils.executeInMainThreadWithResult(
                lambda: cmds.warning(f"Error exporting Alembic: {str(e)}")
            )
            print(f"Error details: {error_details}")
            return False
        finally:
            maya.utils.executeInMainThreadWithResult(
                lambda: [
                    cmds.button(self.export_btn, edit=True, enable=True),
                    self.show_progress_bar(False)
                ]
            )


if __name__ == "__main__":
    bridge = MayaUnrealSocketBridge()
    ui = SocketBridgeUI(bridge)
    ui.create_ui()