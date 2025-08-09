import unreal
import socket
import json
import threading
import time
import os
import queue

HOST = "127.0.0.1"
PORT = 12112
BUFFER_SIZE = 4096

class UnrealMayaSocketClient:
    def __init__(self):
        self.socket = None
        self.is_connected = False
        self.receive_thread = None
        self.response_callbacks = {}
        self.last_command_id = 0
        self.message_queue = queue.Queue()
        self.disconnect_requested = False
        self.timer_handle = None
        self.setup_message_processor()

    def setup_message_processor(self):
        if not self.timer_handle:
            self.timer_handle = unreal.register_slate_post_tick_callback(self.process_message_queue)

    def process_message_queue(self, delta_time):
        try:
            if self.disconnect_requested:
                self._perform_disconnect()
                self.disconnect_requested = False

            while not self.message_queue.empty():
                try:
                    message = self.message_queue.get_nowait()
                    self.process_message(message)
                except queue.Empty:
                    break
        except Exception as e:
            unreal.log_error(f"Error in message processor: {str(e)}")

        return True

    def connect(self):
        if self.is_connected:
            unreal.log("Already connected to Maya")
            return False

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((HOST, PORT))
            self.is_connected = True
            self.disconnect_requested = False

            unreal.log(f"Connected to Maya server at {HOST}:{PORT}")

            self.receive_thread = threading.Thread(target=self.receive_messages)
            self.receive_thread.daemon = True
            self.receive_thread.start()

            self.send_command('ping', {})
            return True
        except Exception as e:
            unreal.log_error(f"Failed to connect to Maya: {str(e)}")
            return False

    def disconnect(self):
        if not self.is_connected:
            unreal.log("Not connected to Maya")
            return
        self.disconnect_requested = True
        unreal.log("Disconnect requested")

    def send_command(self, command, params=None, callback=None):
        if not self.is_connected:
            unreal.log_error("Not connected to Maya server")
            return False
        if params is None:
            params = {}
        self.last_command_id += 1
        command_id = self.last_command_id
        data = {'command': command, 'id': command_id, **params}
        if callback:
            self.response_callbacks[command_id] = callback
        try:
            message = json.dumps(data)
            self.socket.sendall(message.encode('utf-8'))
            unreal.log(f"Sent to Maya: {command} (ID: {command_id})")
            return command_id
        except Exception as e:
            unreal.log_error(f"Error sending command to Maya: {str(e)}")
            self.disconnect()
            return False

    def _perform_disconnect(self):
        unreal.log("Disconnecting from Maya")
        self.is_connected = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        self.response_callbacks = {}
        unreal.log("Disconnected from Maya")

    def receive_messages(self):
        self.socket.settimeout(1.0)
        while self.is_connected:
            try:
                data = self.socket.recv(BUFFER_SIZE)
                if not data:
                    unreal.log("Connection to Maya server closed")
                    break
                message = data.decode('utf-8')
                self.message_queue.put(message)
            except socket.timeout:
                continue
            except Exception as e:
                if self.is_connected:
                    unreal.log_error(f"Error receiving data from Maya: {str(e)}")
                break

        self.disconnect_requested = True

    def process_message(self, message):
        try:
            data = json.loads(message)
            unreal.log(f"Received from Maya: {message}")
            if 'command' in data:
                command = data['command']
                if command == 'import_alembic':
                    file_path = data.get('file_path', '')
                    objects = data.get('objects', [])
                    material_import_method = data.get('material_import_method', 'find')
                    if file_path:
                        unreal.log(f"Importing Alembic from: {file_path}")
                        self.import_alembic(file_path, material_import_method)
                    else:
                        unreal.log_error("No file path provided for Alembic import")

            elif 'status' in data:
                status = data['status']
                if status == 'ok':
                    if data.get('message') == 'pong':
                        unreal.log("Ping successful - Maya server is responsive")
                else:
                    unreal.log_error(f"Error from Maya: {data.get('message', 'Unknown error')}")

        except json.JSONDecodeError:
            unreal.log_error(f"Received invalid JSON from Maya: {message}")
        except Exception as e:
            unreal.log_error(f"Error processing message from Maya: {str(e)}")

    def reimport_alembic(self, existing_asset, source_file_path, material_import_method):
        reimport_task = unreal.AssetImportTask()
        reimport_task.filename = source_file_path
        package_path = unreal.Paths.get_path(existing_asset.package_name)
        reimport_task.destination_path = package_path
        reimport_task.replace_existing = True
        reimport_task.automated = True
        reimport_task.save = True

        options = unreal.AbcImportSettings()
        options.geometry_cache_settings.motion_vectors = unreal.AbcGeometryCacheMotionVectorsImport.IMPORT_ABC_VELOCITIES_AS_MOTION_VECTORS
        options.conversion_settings.scale = unreal.Vector(1.0, -1.0, 1.0)
        options.conversion_settings.rotation = unreal.Vector(90.0, 0.0, 0.0)
        options.material_settings.find_materials = (material_import_method == 'find')
        options.material_settings.create_materials = (material_import_method == 'create')
        reimport_task.options = options

        try:
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([reimport_task])
            unreal.log(f"Reimported Alembic: {existing_asset.package_name}")
            return True
        except Exception as e:
            unreal.log_error(f"Failed to reimport Alembic: {str(e)}")
            return False

    def import_new_alembic(self, file_path, destination_path, material_import_method):
        task = unreal.AssetImportTask()
        task.filename = file_path
        task.destination_path = destination_path
        task.replace_existing = True
        task.automated = True
        task.save = True

        options = unreal.AbcImportSettings()
        options.import_type = unreal.AlembicImportType.GEOMETRY_CACHE
        options.geometry_cache_settings.motion_vectors = unreal.AbcGeometryCacheMotionVectorsImport.IMPORT_ABC_VELOCITIES_AS_MOTION_VECTORS
        options.conversion_settings.flip_u = False
        options.conversion_settings.flip_v = True
        options.conversion_settings.scale = unreal.Vector(1.0, -1.0, 1.0)
        options.conversion_settings.rotation = unreal.Vector(90.0, 0.0, 0.0)
        options.material_settings.find_materials = (material_import_method == 'find')
        options.material_settings.create_materials = (material_import_method == 'create')
        task.options = options

        unreal.log("Executing Alembic import task...")
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

        unreal.log(f"Successfully imported Alembic to {destination_path}")

    def import_alembic(self, file_path, material_import_method='find'):
        try:
            if not os.path.exists(file_path):
                unreal.log_error(f"Alembic file not found: {file_path}")
                return False
            file_name = os.path.basename(file_path)
            base_name = os.path.splitext(file_name)[0]
            selected_path = self.get_selected_content_browser_path()
            if not selected_path:
                unreal.log_error("No folder selected in Content Browser. Please select a destination folder first.")
                return False
            destination_folder = selected_path
            asset_name = base_name
            full_asset_path = f"{destination_folder}/{asset_name}"
            unreal.log(f"Looking for asset at: {full_asset_path}")
            existing_asset = unreal.EditorAssetLibrary.find_asset_data(full_asset_path)
            if existing_asset.is_valid():
                unreal.log(f"Asset already exists at {full_asset_path}. Reimporting...")
                self.reimport_alembic(existing_asset, file_path, material_import_method)
            else:
                unreal.log(f"Importing new Alembic asset to {destination_folder}")
                self.import_new_alembic(file_path, destination_folder, material_import_method)
            return True
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            unreal.log_error(f"Error importing Alembic: {str(e)}")
            unreal.log_error(f"Error details: {error_details}")
            return False

    def get_selected_content_browser_path(self):
        try:
            selected_path = None
            selected_path_view_folders = unreal.EditorUtilityLibrary.get_selected_path_view_folder_paths()
            if selected_path_view_folders and len(selected_path_view_folders) > 0:
                selected_path = selected_path_view_folders[0]

            if not selected_path:
                selected_folders = unreal.EditorUtilityLibrary.get_selected_folder_paths()
                if selected_folders and len(selected_folders) > 0:
                    selected_path = selected_folders[0]

            if selected_path:
                if selected_path.startswith('/All'):
                    selected_path = selected_path[4:]
                if not selected_path.startswith('/Game/'):
                    if selected_path.startswith('/'):
                        selected_path = '/Game' + selected_path
                    else:
                        selected_path = '/Game/' + selected_path

                if selected_path == "/Game/Game":
                    unreal.log_error(
                        "Detected default path '/Game/Game'. Please select a specific folder in Content Browser.")
                    return None
                unreal.log(f"Selected path (cleaned): {selected_path}")
                return selected_path
            else:
                unreal.log_error("No folder selected in Content Browser. Please select a destination folder first.")
                return None
        except Exception as e:
            unreal.log_error(f"Could not get selected Content Browser path: {str(e)}")
            return None


maya_client = UnrealMayaSocketClient()


def connect_to_maya():
    return maya_client.connect()


def disconnect_from_maya():
    maya_client.disconnect()