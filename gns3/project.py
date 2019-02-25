# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 GNS3 Technologies Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import json
import shutil
import uuid

# from gns3server.controller.topology import GNS3_FILE_FORMAT_REVISION

from .qt import QtCore, qpartial, QtWidgets, QtNetwork, qslot

from gns3.controller import Controller
# from gns3.compute_manager import ComputeManager
from gns3.topology import Topology
from gns3.local_config import LocalConfig
from gns3.settings import GRAPHICS_VIEW_SETTINGS
from gns3.appliance_manager import ApplianceManager
from gns3.utils import parse_version

import logging
log = logging.getLogger(__name__)


class Project(QtCore.QObject):

    """Current project"""

    # Called before project closing
    project_about_to_close_signal = QtCore.Signal()

    # Called when the project is closed on all servers
    project_closed_signal = QtCore.Signal()

    # Called when the creation of a project failed, the argument is the error message
    project_creation_error_signal = QtCore.Signal(str)

    project_updated_signal = QtCore.Signal()

    # Called when project is fully loaded
    project_loaded_signal = QtCore.Signal()

    def __init__(self):

        self._id = None
        self._closed = True
        self._closing = False
        self._files_dir = None
        self._images_dir = None
        self._auto_start = False
        self._auto_open = False
        self._auto_close = False

        config = LocalConfig.instance()

        graphic_settings = LocalConfig.instance().loadSectionSettings("GraphicsView", GRAPHICS_VIEW_SETTINGS)
        self._scene_width = graphic_settings["scene_width"]
        self._scene_height = graphic_settings["scene_height"]
        self._zoom = graphic_settings.get("zoom", None)
        self._show_layers = graphic_settings.get("show_layers", False)
        self._snap_to_grid = graphic_settings.get("snap_to_grid", False)
        self._show_grid = graphic_settings.get("show_grid", False)
        self._show_interface_labels = graphic_settings.get("show_interface_labels", False)
        self._show_interface_labels_on_new_project = config.showInterfaceLabelsOnNewProject()

        self._name = "untitled"
        self._filename = None

        # Due to bug in Qt on some version we need a dedicated network manager
        self._notification_network_manager = QtNetwork.QNetworkAccessManager()
        self._notification_stream = None

        super().__init__()

    def name(self):
        """
        :returns: Project name (string)
        """

        return self._name

    def setSceneWidth(self, val):
        self._scene_width = val

    def sceneWidth(self):
        return self._scene_width

    def setSceneHeight(self, val):
        self._scene_height = val

    def sceneHeight(self):
        return self._scene_height

    def setAutoOpen(self, val):
        """
        Open the project with GNS3 server
        """
        self._auto_open = val

    def autoOpen(self):
        return self._auto_open

    def setAutoClose(self, val):
        """
        Close the project when last client is disconnected from the notification feed
        """
        self._auto_close = val

    def autoClose(self):
        return self._auto_close

    def setAutoStart(self, val):
        """
        Start the project when opened
        """
        self._auto_start = val

    def autoStart(self):
        return self._auto_start

    def setZoom(self, zoom):
        """
        Sets zoom factor of the view
        """
        self._zoom = zoom

    def zoom(self):
        """
        Returns zoom factor of project
        :return: float or None when not defined
        """
        return self._zoom

    def setShowLayers(self, show_layers):
        """
        Sets show layers mode
        """
        self._show_layers = show_layers

    def showLayers(self):
        """
        Returns if show layers mode is ON
        :return: boolean
        """
        return self._show_layers

    def setSnapToGrid(self, snap_to_grid):
        """
        Sets snap to grid mode
        """
        self._snap_to_grid = snap_to_grid

    def snapToGrid(self):
        """
        Returns if snap to grid mode is ON
        :return: boolean
        """
        return self._snap_to_grid

    def setShowGrid(self, show_grid):
        """
        Sets show grid mode
        """
        self._show_grid = show_grid

    def showGrid(self):
        """
        Returns if show grid mode is ON
        :return: boolean
        """
        return self._show_grid

    def setShowInterfaceLabels(self, show_interface_labels):
        """
        Sets show interface labels mode
        """
        self._show_interface_labels = show_interface_labels

    def showInterfaceLabels(self):
        """
        Returns if show interface labels mode is ON
        :return: boolean
        """
        return self._show_interface_labels

    def setName(self, name):
        """
        Set project name

        :param name: Project name (string)
        """

        assert name is not None
        if len(name) > 0:
            self._name = name

    def closed(self):
        """
        :returns: True if project is closed
        """

        return self._closed

    def id(self):
        """
        Get project identifier
        """

        return self._id

    def setId(self, project_id):
        """
        Set project identifier
        """

        self._id = project_id

    def path(self):
        """
        Return the path of the .gns3
        """
        if self._files_dir:
            return os.path.join(self._files_dir, self._filename)
        return None

    def filesDir(self):
        """
        Project directory on the local server
        """

        return self._files_dir

    def setFilesDir(self, files_dir):

        self._files_dir = files_dir

    def filename(self):
        """
        Project filename
        """
        return self._filename

    def setFilename(self, name):
        """
        Set project filename
        """
        self._filename = name

    def project_to_topology(project):
        """
        :return: A dictionnary with the topology ready to dump to a .gns3
        """
        data = {
            "project_id": project.id(),
            "name": project.name(),
            "auto_start": project._auto_start,
            "auto_open": project._auto_open,
            "auto_close": project._auto_close,
            "scene_width": project._scene_width,
            "scene_height": project._scene_height,
            "zoom": project._zoom,
            "show_layers": project._show_layers,
            "snap_to_grid": project._snap_to_grid,
            "show_grid": project._show_grid,
            "show_interface_labels": project._show_interface_labels,
            "topology": {
                "nodes": [],
                "links": [],
                "computes": [],
                "drawings": []
            },
            "type": "topology",
            "revision": "GNS3_FILE_FORMAT_REVISION",
            "version": "0.1"
        }

        topo = Topology.instance()
        computes = set()
        for node in topo.nodes():
            computes.add(node.compute)
            data["topology"]["nodes"].append(node.__json__())
        for link in topo.links():
            print(link.__json__())
            data["topology"]["links"].append(link.__json__())
        for drawing in topo.drawings():
            data["topology"]["drawings"].append(drawing.__json__())
        for compute in computes:
            if hasattr(compute, "__json__"):
                compute = compute.__json__()
                if compute["compute_id"] not in ("vm", "local",):
                    data["topology"]["computes"].append(compute)
        # _check_topology_schema(data)
        print(data)
        return data

    def dump(self):
        """
        Dump topology to disk
        """
        try:
            topo = self.project_to_topology()
            path = self.path()
            os.makedirs(os.path.dirname(self.path()), exist_ok=True)
            log.debug("Write %s", path)
            with open(path + ".tmp", "w+", encoding="utf-8") as f:
                json.dump(topo, f, indent=4, sort_keys=True)
            shutil.move(path + ".tmp", path)
        except OSError as e:
            print("Could not write topology: {}".format(e))
            # raise aiohttp.web.HTTPInternalServerError(text="Could not write topology: {}".format(e))

    def load_topology(self):
        """
        Open a topology file, patch it for last GNS3 release and return it
        """
        path = self.path()
        log.debug("Read topology %s", path)
        try:
            with open(path, encoding="utf-8") as f:
                topo = json.load(f)
        except (OSError, UnicodeDecodeError, ValueError) as e:
            raise Exception("Could not load topology {}: {}".format(path, str(e)))
        return topo

    def open(self):
        """
        Load topology elements
        """
        self._status = "closed"
        if self._status == "opened":
            return

        # self.reset()
        self._loading = True
        self._status = "opened"

        # path = self._topology_file()
        # if not os.path.exists(path):
        #     self._loading = False
        #     return
        # try:
        #     shutil.copy(path, path + ".backup")
        # except OSError:
        #     pass
        # try:
        project_data = self.load_topology()

        # load meta of project
        keys_to_load = [
            "auto_start",
            "auto_close",
            "auto_open",
            "scene_height",
            "scene_width",
            "zoom",
            "show_layers",
            "snap_to_grid",
            "show_grid",
            "show_interface_labels"
        ]

        for key in keys_to_load:
            val = project_data.get(key, None)
            if val is not None:
                setattr(self, key, val)

        topo = Topology.instance()
        topo.setProject(self)

        topology = project_data["topology"]
        for compute in topology.get("computes", []):
            self.controller.add_compute(**compute)
        for node in topology.get("nodes", []):
            topo.createNode(node)
            # compute = self.controller.get_compute(node.pop("compute_id"))
            # name = node.pop("name")
            # node_id = node.pop("node_id", str(uuid.uuid4()))
            # yield from self.add_node(compute, name, node_id, dump=False, **node)
        for link_data in topology.get("links", []):
            if 'link_id' not in link_data.keys():
                # skip the link
                continue
            link = topo.createLink(link_data)  # self.add_link(link_id=link_data["link_id"])
            # if "filters" in link_data:
            #    link.update_filters(link_data["filters"])
            # for node_link in link_data["nodes"]:
            #     node = self.get_node(node_link["node_id"])
            #     port = node.get_port(node_link["adapter_number"], node_link["port_number"])
            #     if port is None:
            #         log.warning("Port {}/{} for {} not found".format(node_link["adapter_number"], node_link["port_number"], node.name))
            #         continue
            #     if port.link is not None:
            #         log.warning("Port {}/{} is already connected to link ID {}".format(node_link["adapter_number"], node_link["port_number"], port.link.id))
            #         continue
            #     link.add_node(node, node_link["adapter_number"], node_link["port_number"], label=node_link.get("label"), dump=False)
            # if len(link.nodes) != 2:
            #     # a link should have 2 attached nodes, this can happen with corrupted projects
            #     self.delete_link(link.id, force_delete=True)
        for drawing_data in topology.get("drawings", []):
            topo.createDrawing(drawing_data)

        # self.dump()
        # We catch all error to be able to rollback the .gns3 to the previous state
        # except Exception as e:
        #     raise Exception("Could not load topology: {}".format(str(e)))
            # try:
            #     if os.path.exists(path + ".backup"):
            #         shutil.copy(path + ".backup", path)
            # except (PermissionError, OSError):
            #     pass
            # self._status = "closed"
            # self._loading = False
        # try:
        #     os.remove(path + ".backup")
        # except OSError:
        #     pass

        # self._loading = False
        # Should we start the nodes when project is open