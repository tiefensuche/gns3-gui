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
import hashlib
import shutil
import tempfile
import asyncio
from uuid import uuid4

from .qt import QtCore, QtGui, QtWidgets, qpartial, qslot
from .symbol import Symbol
from .local_server_config import LocalServerConfig
from .settings import LOCAL_SERVER_SETTINGS

import logging
log = logging.getLogger(__name__)


class Controller(QtCore.QObject):
    """
    An instance of the GNS3 server controller
    """
    connected_signal = QtCore.Signal()
    disconnected_signal = QtCore.Signal()
    connection_failed_signal = QtCore.Signal()
    project_list_updated_signal = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__()
        self._connected = True
        self._connecting = False
        self._cache_directory = tempfile.mkdtemp()
        self._http_client = None
        # If it's the first error we display an alert box to the user
        self._first_error = True
        self._error_dialog = None
        self._display_error = True
        self._projects = {}

        # If we do multiple call in order to download the same symbol we queue them
        self._static_asset_download_queue = {}

    @staticmethod
    def instance():
        """
        Singleton to return only on instance of Controller.
        :returns: instance of Controller
        """

        if not hasattr(Controller, '_instance') or Controller._instance is None:
            Controller._instance = Controller()
        return Controller._instance

    def getStatic(self, url, callback, fallback=None):
        """
        Get a URL from the /static on controller and cache it on disk

        :param url: URL without the protocol and host part
        :param callback: Callback to call when file is ready
        :param fallback: Fallback url in case of error
        """

        if not self._http_client:
            return


        path = self.getStaticCachedPath(url)

        if os.path.exists(path):
            callback(path)
        elif path in self._static_asset_download_queue:
            self._static_asset_download_queue[path].append((callback, fallback, ))
        else:
            self._static_asset_download_queue[path] = [(callback, fallback, )]
            self._http_client.createHTTPQuery("GET", url, qpartial(self._getStaticCallback, url, path))

    def _getStaticCallback(self, url, path, result, error=False, raw_body=None, **kwargs):
        if path not in self._static_asset_download_queue:
            return

        if error:
            fallback_used = False
            for callback, fallback in self._static_asset_download_queue[path]:
                if fallback:
                    self.getStatic(fallback, callback)
                fallback_used = True
            if fallback_used:
                log.debug("Error while downloading file: {}".format(url))
            del self._static_asset_download_queue[path]
            return
        try:
            with open(path, "wb+") as f:
                f.write(raw_body)
        except OSError as e:
            log.error("Can't write to {}: {}".format(path, str(e)))
            return
        log.debug("File stored {} for {}".format(path, url))
        for callback, fallback in self._static_asset_download_queue[path]:
            callback(path)
        del self._static_asset_download_queue[path]

    def getStaticCachedPath(self, url):
        """
        Returns static cached (hashed) path
        :param url:
        :return:
        """
        m = hashlib.md5()
        m.update(url.encode())
        if ".svg" in url:
            extension = ".svg"
        else:
            extension = ".png"
        path = os.path.join(self._cache_directory, m.hexdigest() + extension)
        return path

    def getSymbolIcon(self, symbol_id, callback, fallback=None):
        """
        Get a QIcon for a symbol from the controller

        :param symbol_id: Symbol id
        :param callback: Callback to call when file is ready
        :param fallback: Fallback symbol if not found
        """
        if symbol_id is None:
            self.getStatic(Symbol(fallback).url(), qpartial(self._getIconCallback, callback))
        else:
            if fallback:
                fallback = Symbol(fallback).url()
            self.getStatic(Symbol(symbol_id).url(), qpartial(self._getIconCallback, callback), fallback=fallback)

    def _getIconCallback(self, callback, path):
        icon = QtGui.QIcon()
        icon.addFile(path)
        callback(icon)

    def getSymbols(self, callback):
        raise Exception("YEA")
        self.get('/symbols', callback=callback)

    def deleteProject(self, project_id, callback=None):
        # Controller.instance().delete("/projects/{}".format(project_id), qpartial(self._deleteProjectCallback, callback=callback, project_id=project_id))
        shutil.rmtree(self._projects[project_id]['name'])
        del self._projects[project_id]
        self.refreshProjectList()


    def _deleteProjectCallback(self, result, error=False, project_id=None, callback=None, **kwargs):
        if error:
            log.error("Error while deleting project: {}".format(result["message"]))
        else:
            self.refreshProjectList()

        self._projects = [p for p in self._projects if p["project_id"] != project_id]

        if callback:
            callback(result, error=error, **kwargs)

    @qslot
    def refreshProjectList(self, *args):
        # self.get("/projects", self._projectListCallback)
        # self.create_project(name="test", path="test")
        self.load_projects()

    def _projectListCallback(self, result, error=False, **kwargs):
        if not error:
            self._projects = result
        self.project_list_updated_signal.emit()

    def create_project(self, name=None, project_id=None, path=None):
        """
        Create a project and keep a references to it in project manager.

        See documentation of Project for arguments
        """

        if project_id is not None and project_id in self._projects:
            return self._projects[project_id]
        project = {"name": name, "id": project_id, "path": path}
        self._projects[project['id']] = project
        self.project_list_updated_signal.emit()
        return project

    def projects(self):
        return self._projects.values()

    def load_topology(self, path):
        """
        Open a topology file, patch it for last GNS3 release and return it
        """
        log.debug("Read topology %s", path)
        try:
            with open(path, encoding="utf-8") as f:
                topo = json.load(f)
        except (OSError, UnicodeDecodeError, ValueError) as e:
            raise Exception("Could not load topology {}: {}".format(path, str(e)))

        return topo

    def add_project(self, project_id=None, name=None, **kwargs):
        """
        Creates a project or returns an existing project

        :param project_id: Project ID
        :param name: Project name
        :param kwargs: See the documentation of Project
        """
        if project_id not in self._projects:

            # for project in self._projects.values():
                # if name and project.name == name:
                #     raise aiohttp.web.HTTPConflict(text='Project name "{}" already exists'.format(name))
            projects_path = os.path.expanduser("~/GNS3/projects")
            path = os.path.join(projects_path, name)
            project = {"id": project_id, "name": name, "path": path, **kwargs}
            self._projects[project_id] = project
            return self._projects[project_id]
        return self._projects[project_id]

    def load_project(self, path, load=True):
        """
        Load a project from a .gns3

        :param path: Path of the .gns3
        :param load: Load the topology
        """
        topo_data = self.load_topology(path)
        topo_data.pop("topology")
        topo_data.pop("version")
        topo_data.pop("revision")
        topo_data.pop("type")

        if topo_data["project_id"] in self._projects:
            project = self._projects[topo_data["project_id"]]
        else:
            project = self.add_project(path=os.path.dirname(path), status="closed", filename=os.path.basename(path), **topo_data)
        # if load:
        #     project.open()
        return project

    def load_projects(self):
        """
        Preload the list of projects from disk
        """
        # server_config = Config.instance().get_section_config("Server")
        projects_path = os.path.expanduser("~/GNS3/projects")
        os.makedirs(projects_path, exist_ok=True)
        try:
            for project_path in os.listdir(projects_path):
                project_dir = os.path.join(projects_path, project_path)
                if os.path.isdir(project_dir):
                    for file in os.listdir(project_dir):
                        if file.endswith(".gns3"):
                            self.load_project(os.path.join(project_dir, file), load=False)
        except OSError as e:
            log.error(str(e))
        self.project_list_updated_signal.emit()

