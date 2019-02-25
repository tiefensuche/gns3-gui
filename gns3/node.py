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


import uuid
import pathlib

from gns3.controller import Controller
from gns3.ports.ethernet_port import EthernetPort
from gns3.ports.serial_port import SerialPort
from gns3.utils.bring_to_front import bring_window_to_front_from_title
from gns3.qt import QtGui, QtCore

from .base_node import BaseNode

import logging
log = logging.getLogger(__name__)


class Node(BaseNode):

    def __init__(self, module, compute, project):

        super().__init__(module, compute, project)

        self._node_id = str(uuid.uuid4())

        self._node_directory = None
        self._command_line = None
        self._always_on = False

        # minimum required base settings
        self._settings = {"name": "", "x": None, "y": None, "z": 1, "label": {"text": "text"}}

    def settings(self):
        return self._settings

    def setSettingValue(self, key, value):
        """
        Set settings
        """
        self._settings[key] = value

    def setGraphics(self, node_item):
        """
        Sync the remote object with the node_item
        """

        data = {
            "x": int(node_item.pos().x()),
            "y": int(node_item.pos().y()),
            "z": int(node_item.zValue()),
            "symbol": node_item.symbol()
        }
        if node_item.label() is not None:
            data["label"] = node_item.label().dump()

        # FIXME merge node.py and node_item.py together?
        # so that no syncing like this is required or keep
        # splitting, e.g. node.py -> model, node_item -> view
        for k, v in data.items():
            self._settings[k] = v

    def setSymbol(self, symbol):
        self._settings["symbol"] = symbol

    def symbol(self):
        return self._settings["symbol"]

    def setPos(self, x, y):
        self._settings["x"] = int(x)
        self._settings["y"] = int(y)

    def x(self):
        return self._settings["x"]

    def y(self):
        return self._settings["y"]

    def z(self):
        return self._settings["z"]

    def node_id(self):
        """
        Return the ID of this device

        :returns: identifier (string)
        """

        return self._node_id

    def _parseResponse(self, result):
        """
        Parse node object from API
        """
        if "node_id" in result:
            self._node_id = result["node_id"]

        if "name" in result:
            self.setName(result["name"])

        if "command_line" in result:
            self._command_line = result["command_line"]

        if "node_directory" in result:
            self._node_directory = result["node_directory"]

        if "status" in result:
            if result["status"] == "started":
                self.setStatus(Node.started)
            elif result["status"] == "stopped":
                self.setStatus(Node.stopped)
            elif result["status"] == "suspended":
                self.setStatus(Node.suspended)

        if "ports" in result:
            self._updatePorts(result["ports"])

        if "properties" in result:
            for name, value in result["properties"].items():
                if name in self._settings and self._settings[name] != value:
                    log.debug("{} setting up and updating {} from '{}' to '{}'".format(self.name(), name, self._settings[name], value))
                    self._settings[name] = value

            result.update(result["properties"])
            del result["properties"]

        # Update common element of all nodes
        for key in ["x", "y", "z", "symbol", "label", "console_host", "console", "console_type"]:
            if key in result:
                self._settings[key] = result[key]

        return result

    def _updatePorts(self, ports):
        self._settings["ports"] = ports
        old_ports = self._ports.copy()
        self._ports = []
        for port in ports:
            new_port = None

            # Update port if already exist
            for old_port in old_ports:
                if old_port.adapterNumber() == port["adapter_number"] and old_port.portNumber() == port[
                    "port_number"] and old_port.name() == port["name"]:
                    new_port = old_port
                    old_ports.remove(old_port)
                    break

            if new_port is None:
                if port["link_type"] == "serial":
                    new_port = SerialPort(port["name"])
                else:
                    new_port = EthernetPort(port["name"])
            new_port.setShortName(port["short_name"])
            new_port.setAdapterNumber(port["adapter_number"])
            new_port.setPortNumber(port["port_number"])
            new_port.setDataLinkTypes(port["data_link_types"])
            new_port.setStatus(self.status())
            self._ports.append(new_port)

    def createNodeCallback(self, result, error=False, **kwargs):
        """
        Callback for create.

        :param result: server response
        :param error: indicates an error (boolean)
        :returns: Boolean success or not
        """
        if error:
            self.server_error_signal.emit(self.id(), "Error while setting up node: {}".format(result["message"]))
            self.deleted_signal.emit()
            self._module.removeNode(self)
            return False

        result = self._parseResponse(result)
        self._createCallback(result)

        if self._loading:
            self.loaded_signal.emit()
        else:
            self.setInitialized(True)
            self.created_signal.emit(self.id())
            self._module.addNode(self)

    def delete(self, skip_controller=False):
        """
        Deletes this node instance.

        :param skip_controller: True to not delete on the controller (often it's when it's already deleted on the server)
        """

        self.deleted_signal.emit()
        self._module.removeNode(self)


    def bringToFront(self):
        """
        Bring the console window to front.
        """

        if self.status() == Node.started:
            if bring_window_to_front_from_title(self.name()):
                return True
            else:
                log.debug("Could not find window title '{}' to bring it to front".format(self.name()))
        return False

    def setName(self, name):
        """
        Set a name for a node.

        :param name: node name
        """

        self._settings["name"] = name

    def name(self):
        """
        Returns the name of this node.

        :returns: name (string)
        """

        return self._settings["name"]
