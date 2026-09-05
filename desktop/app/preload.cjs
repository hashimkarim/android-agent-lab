'use strict';
const {contextBridge, ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('lab', {
  request: (action, data) => ipcRenderer.invoke('lab:request', action, data),
  onUpdate: (callback) => ipcRenderer.on('lab:update', (_event, value) => callback(value)),
});
