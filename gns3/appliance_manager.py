#!/usr/bin/env python
#
# Copyright (C) 2016 GNS3 Technologies Inc.
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
import json
import os
import uuid

from gns3.utils.get_resource import get_resource

from .qt import QtCore
from .controller import Controller
from .utils.server_select import server_select

import logging
log = logging.getLogger(__name__)


import copy


# Convert old GUI category to text category
ID_TO_CATEGORY = {
    3: "firewall",
    2: "guest",
    1: "switch",
    0: "router"
}


class Appliance:

    def __init__(self, appliance_id, data, builtin=False):
        if appliance_id is None:
            self._id = str(uuid.uuid4())
        elif isinstance(appliance_id, uuid.UUID):
            self._id = str(appliance_id)
        else:
            self._id = appliance_id
        self._data = data.copy()
        if "appliance_id" in self._data:
            del self._data["appliance_id"]

        # Version of the gui before 2.1 use linked_base
        # and the server linked_clone
        if "linked_base" in self._data:
            linked_base = self._data.pop("linked_base")
            if "linked_clone" not in self._data:
                self._data["linked_clone"] = linked_base
        if data["node_type"] == "iou" and "image" in data:
            del self._data["image"]
        self._builtin = builtin

    @property
    def id(self):
        return self._id

    @property
    def data(self):
        return copy.deepcopy(self._data)

    @property
    def name(self):
        return self._data["name"]

    @property
    def compute_id(self):
        return self._data.get("server")

    @property
    def builtin(self):
        return self._builtin

    def __json__(self):
        """
        Appliance data (a hash)
        """
        try:
            category = ID_TO_CATEGORY[self._data["category"]]
        except KeyError:
            category = self._data["category"]

        return {
            "appliance_id": self._id,
            "node_type": self._data["node_type"],
            "name": self._data["name"],
            "default_name_format": self._data.get("default_name_format", "{name}-{0}"),
            "category": category,
            "symbol": self._data.get("symbol", ":/symbols/computer.svg"),
            "compute_id": self.compute_id,
            "builtin": self._builtin,
            "platform": self._data.get("platform", None)
        }


class ApplianceManager(QtCore.QObject):

    appliances_changed_signal = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._appliance_templates = []
        self._appliances = {}
        self._controller = Controller.instance()
        self._controller.connected_signal.connect(self.refresh)
        self._controller.disconnected_signal.connect(self._controllerDisconnectedSlot)
        self.refresh()

    def load_settings(self):
        with open("/home/fabi/.config/GNS3/gns3_controller.conf") as f:
            data = json.load(f)
        self._settings = data["settings"]

    def load_appliances(self):
        self.load_settings()
        # self._appliances = {}
        app = Appliance(uuid.uuid3(uuid.NAMESPACE_DNS, "ethernet_switch"),
                  {"node_type": "ethernet_switch", "name": "Ethernet switch", "category": 1,
                   "symbol": ":/symbols/ethernet_switch.svg"}, builtin=True)
        self._appliances[app.id] = app.__json__()

        vms = []
        for vm in self._settings.get("Qemu", {}).get("vms", []):
            vm["node_type"] = "qemu"
            vms.append(vm)
        for vm in self._settings.get("IOU", {}).get("devices", []):
            vm["node_type"] = "iou"
            vms.append(vm)
        for vm in self._settings.get("Docker", {}).get("containers", []):
            vm["node_type"] = "docker"
            vms.append(vm)
        for vm in self._settings.get("Builtin", {}).get("cloud_nodes", []):
            vm["node_type"] = "cloud"
            vms.append(vm)
        for vm in self._settings.get("Builtin", {}).get("ethernet_switches", []):
            vm["node_type"] = "ethernet_switch"
            vms.append(vm)
        for vm in self._settings.get("Builtin", {}).get("ethernet_hubs", []):
            vm["node_type"] = "ethernet_hub"
            vms.append(vm)
        for vm in self._settings.get("Dynamips", {}).get("routers", []):
            vm["node_type"] = "dynamips"
            vms.append(vm)
        for vm in self._settings.get("VMware", {}).get("vms", []):
            vm["node_type"] = "vmware"
            vms.append(vm)
        for vm in self._settings.get("VirtualBox", {}).get("vms", []):
            vm["node_type"] = "virtualbox"
            vms.append(vm)
        for vm in self._settings.get("VPCS", {}).get("nodes", []):
            vm["node_type"] = "vpcs"
            vms.append(vm)

        for vm in vms:
            # remove deprecated properties
            for prop in vm.copy():
                if prop in ["enable_remote_console", "use_ubridge"]:
                    del vm[prop]

            # remove deprecated default_symbol and hover_symbol
            # and set symbol if not present
            deprecated = ["default_symbol", "hover_symbol"]
            if len([prop for prop in vm.keys() if prop in deprecated]) > 0:
                if "default_symbol" in vm.keys():
                    del vm["default_symbol"]
                if "hover_symbol" in vm.keys():
                    del vm["hover_symbol"]

                if "symbol" not in vm.keys():
                    vm["symbol"] = ":/symbols/computer.svg"

            vm.setdefault("appliance_id", str(uuid.uuid4()))
            try:
                appliance = Appliance(vm["appliance_id"], vm)
                appliance.__json__()  # Check if loaded without error
                self._appliances[appliance.id] = appliance.__json__()
            except KeyError as e:
                # appliance data is not complete (missing name or type)
                log.warning("Cannot load appliance template {} ('{}'): missing key {}".format(vm["appliance_id"], vm.get("name", "unknown"), e))
                continue

    def refresh(self):
        self.load_appliances()
        print(self._appliances)
        # if self._controller.connected():
        #     self._controller.get("/appliances/templates", self._listApplianceTemplateCallback)
        #     self._controller.get("/appliances", self._listAppliancesCallback)

    def _controllerDisconnectedSlot(self):
        self._appliance_templates = []
        self._appliances = []
        self.appliances_changed_signal.emit()

    def appliance_templates(self):
        return self._appliance_templates

    def appliances(self):
        return self._appliances

    def getAppliance(self, appliance_id):
        """
        Look for an appliance by appliance ID
        """
        # for appliance in self._appliances:
        #     if appliance.id == appliance_id:
        #         return appliance
        # return None
        return self._appliances[appliance_id]

    def _listAppliancesCallback(self, result, error=False, **kwargs):
        if error is True:
            log.error("Error while getting appliances list: {}".format(result["message"]))
            return
        self._appliances = result
        self.appliances_changed_signal.emit()

    def _listApplianceTemplateCallback(self, result, error=False, **kwargs):
        if error is True:
            log.error("Error while getting appliance templates list: {}".format(result["message"]))
            return
        self._appliance_templates = result
        self.appliances_changed_signal.emit()

    def createNodeFromApplianceId(self, project, appliance_id, x, y):
        from gns3.topology import Topology
        app = self._appliances[appliance_id]
        Topology.instance().createNode(node_data={"node_type": app["node_type"], "x": x, "y": y, "symbol": app["symbol"]})
        return True

        for appliance in self._appliances:
            if appliance["appliance_id"] == appliance_id:
                break

        project_id = project.id()

        if appliance.get("compute_id") is None:
            from .main_window import MainWindow
            server = server_select(MainWindow.instance(), node_type=appliance["node_type"])
            if server is None:
                return False
            self._controller.post("/projects/" + project_id + "/appliances/" + appliance_id, self._createNodeFromApplianceCallback, {
                "compute_id": server.id(),
                "x": int(x),
                "y": int(y)
            },
                timeout=None)
        else:
            self._controller.post("/projects/" + project_id + "/appliances/" + appliance_id, self._createNodeFromApplianceCallback, {
                "x": int(x),
                "y": int(y)
            },
                timeout=None)
        return True

    def _createNodeFromApplianceCallback(self, result, error=False, **kwargs):
        if error:
            if "message" in result:
                log.error("Error while creating node: {}".format(result["message"]))
            return

    @staticmethod
    def instance():
        """
        Singleton to return only on instance of ApplianceManager.
        :returns: instance of ApplianceManager
        """

        if not hasattr(ApplianceManager, '_instance') or ApplianceManager._instance is None:
            ApplianceManager._instance = ApplianceManager()
        return ApplianceManager._instance
