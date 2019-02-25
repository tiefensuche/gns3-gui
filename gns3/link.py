# -*- coding: utf-8 -*-
#
# Copyright (C) 2013 GNS3 Technologies Inc.
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

"""
Manages and stores everything needed for a connection between 2 devices.
"""

import os
import re
import sip
import uuid

from .qt import QtCore, QtWidgets
from .controller import Controller


import logging
log = logging.getLogger(__name__)


class Link(QtCore.QObject):

    """
    Link implementation.

    :param source_node: source Node instance
    :param source_port: source Port instance
    :param destination_node: destination Node instance
    :param destination_port: destination Port instance
    """

    # signals used to let the GUI view know about link
    # additions and deletions.
    add_link_signal = QtCore.Signal(int)
    delete_link_signal = QtCore.Signal(int)
    updated_link_signal = QtCore.Signal(int)
    error_link_signal = QtCore.Signal(int)

    _instance_count = 1

    def __init__(self, source_node, source_port, destination_node, destination_port, link_id=None, **link_data):
        """
        :param link_data: Link information from the API
        """

        super().__init__()

        log.debug("adding link from {} {} to {} {}".format(source_node.name(),
                                                           source_port.name(),
                                                           destination_node.name(),
                                                           destination_port.name()))

        # create an unique ID
        self._id = Link._instance_count
        Link._instance_count += 1

        self._source_node = source_node
        self._source_port = source_port
        self._destination_node = destination_node
        self._destination_port = destination_port
        self._source_label = None
        self._destination_label = None
        self._link_id = link_id
        self._capturing = False
        self._capture_file_path = None
        self._capture_file = None
        self._initialized = True
        self._filters = {}
        self._suspend = False

        # Boolean if True we are creating the first instance of this node
        # if false the node already exist in the topology
        # use to avoid erasing information when reloading
        self._creator = False

        self._nodes = []

        self._source_node.addLink(self)
        self._destination_node.addLink(self)

        if self._link_id:
            self._link_id = str(uuid.uuid4())

        link_data["link_id"] = self._link_id
        self._linkCreatedCallback(link_data)

    def _parseResponse(self, result):
        if "nodes" in result:
            self._nodes = result["nodes"]
            # self._updateLabels()
        if "filters" in result:
            self._filters = result["filters"]
        if "suspend" in result:
            self._suspend = result["suspend"]
        self.updated_link_signal.emit(self._id)

    def creator(self):
        return self._creator

    def suspended(self):
        return self._suspend

    def toggleSuspend(self):
        self._suspend = not self._suspend
        self.update()

    def initialized(self):
        return self._initialized

    def addPortLabel(self, port, label):
        if port.adapterNumber() == self._source_port.adapterNumber() and port.portNumber() == self._source_port.portNumber() and port.destinationNode() == self._destination_node:
            self._source_label = label
        else:
            self._destination_label = label
        # FIXME
        # label.item_unselected_signal.connect(self.update)
        # if self.creator():
        #     self.update()
        # else:
        #     self._updateLabels()

    def updateLinkCallback(self, result, error=False, *args, **kwargs):
        if error:
            QtWidgets.QMessageBox.warning(None, "Update link", "Error while updating link: {}".format(result["message"]))
            return
        self._parseResponse(result)

    def _updateLabels(self):
        for node in self._nodes:
            if node["node_id"] == self._source_node.node_id() and node["adapter_number"] == self._source_port.adapterNumber() and node["port_number"] == self._source_port.portNumber():
                self._updateLabel(self._source_label, node["label"])
            elif node["node_id"] == self._destination_node.node_id() and node["adapter_number"] == self._destination_port.adapterNumber() and node["port_number"] == self._destination_port.portNumber():
                self._updateLabel(self._destination_label, node["label"])
            else:
                raise NotImplementedError

    def _updateLabel(self, label, label_data):
        if not label or sip.isdeleted(label):
            return
        if "text" in label_data:
            label.setPlainText(label_data["text"])
        if "x" in label_data and "y" in label_data:
            label.setPos(label_data["x"], label_data["y"])
        if "style" in label_data:
            label.setStyle(label_data["style"])
        if "rotation" in label_data:
            label.setRotation(label_data["rotation"])

    def _prepareParams(self):
        body = {
            "nodes": [
                {
                    "node_id": self._source_node.node_id(),
                    "adapter_number": self._source_port.adapterNumber(),
                    "port_number": self._source_port.portNumber(),
                },
                {
                    "node_id": self._destination_node.node_id(),
                    "adapter_number": self._destination_port.adapterNumber(),
                    "port_number": self._destination_port.portNumber()
                }
            ],
            "filters": self._filters,
            "suspend": self._suspend
        }
        if self._source_port.label():
            body["nodes"][0]["label"] = self._source_port.label().dump()
        if self._destination_port.label():
            body["nodes"][1]["label"] = self._destination_port.label().dump()
        return body

    def _linkCreatedCallback(self, result, error=False, **kwargs):
        if error:
            QtWidgets.QMessageBox.warning(None, "Create link", "Error while creating link: {}".format(result["message"]))
            self.deleteLink(skip_controller=True)
            return

        self._initialized = True

        # let the GUI know about this link has been created
        self.add_link_signal.emit(self._id)
        self._source_port.setLinkId(self._id)
        self._source_port.setLink(self)
        self._source_port.setDestinationNode(self._destination_node)
        self._source_port.setDestinationPort(self._destination_port)
        self._destination_port.setLinkId(self._id)
        self._destination_port.setLink(self)
        self._destination_port.setDestinationNode(self._source_node)
        self._destination_port.setDestinationPort(self._source_port)

        self._link_id = result["link_id"]
        self._parseResponse(result)

    def link_id(self):
        return self._link_id

    def capturing(self):
        """
        Is a capture running on the link?
        """
        return self._capturing

    def capture_file_path(self):
        """
        Path of the capture file
        """
        return self._capture_file_path

    def project(self):
        return self._source_node.project()

    @classmethod
    def reset(cls):
        """
        Reset the instance count.
        """

        cls._instance_count = 1

    def __str__(self):

        description = "Link from {} port {} to {} port {}".format(self._source_node.name(),
                                                                  self._source_port.name(),
                                                                  self._destination_node.name(),
                                                                  self._destination_port.name())

        if self.capturing():
            description += "\nPacket capture is active"

        for filter_type in self._filters.keys():
            description += "\nPacket filter '{}' is active".format(filter_type)

        return description

    def deleteLink(self, skip_controller=False):
        """
        Deletes this link.
        """

        log.debug("deleting link from {} {} to {} {}".format(self._source_node.name(),
                                                             self._source_port.name(),
                                                             self._destination_node.name(),
                                                             self._destination_port.name()))
        self._linkDeletedCallback({})

    def _linkDeletedCallback(self, result, error=False, **kwargs):
        """
        Called after the link is remove from the topology
        """
        if error:
            log.error("Error while deleting link: {}".format(result["message"]))
            return

        self._source_port.setFree()
        self._source_node.deleteLink(self)
        self._source_node.updated_signal.emit()
        self._destination_port.setFree()
        self._destination_node.deleteLink(self)
        self._destination_node.updated_signal.emit()

        # let the GUI know about this link has been deleted
        self.delete_link_signal.emit(self._id)

    def id(self):
        """
        Returns this link identifier.

        :returns: link identifier (integer)
        """

        return self._id

    def sourceNode(self):
        """
        Returns the source node for this link.

        :returns: Node instance
        """

        return self._source_node

    def destinationNode(self):
        """
        Returns the destination node for this link.

        :returns: Node instance
        """

        return self._destination_node

    def sourcePort(self):
        """
        Returns the source port for this link.

        :returns: Port instance
        """

        return self._source_port

    def destinationPort(self):
        """
        Returns the destination port for this link.

        :returns: Port instance
        """

        return self._destination_port

    def getNodePort(self, node):
        """
        Search the port in the link corresponding to this node

        :returns: Node instance
        """
        if self._destination_node == node:
            return self._destination_port
        return self._source_port

    def filters(self):
        """
        :returns: List the filters active on the node
        """
        return self._filters

    def setFilters(self, filters):
        """
        :params filters: List of filters
        """
        self._filters = filters

    def __json__(self):
        return {
            "link_id": self._link_id,
            "nodes": [{"node_id": self._source_node.id(),
                       "adapter_number": self._source_port.adapterNumber(),
                       "port_number": self._source_port.portNumber()},
                      {"node_id": self._destination_node.id(),
                       "adapter_number": self._destination_port.adapterNumber(),
                       "port_number": self._destination_port.portNumber()}
                      ]
        }
