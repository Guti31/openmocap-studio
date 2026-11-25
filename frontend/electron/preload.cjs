const { contextBridge, ipcRenderer } = require('electron');

function subscribe(channel, callback) {
  if (typeof callback !== 'function') return () => {};
  const listener = (_event, payload) => callback(payload);
  ipcRenderer.on(channel, listener);
  return () => {
    ipcRenderer.removeListener(channel, listener);
  };
}

contextBridge.exposeInMainWorld('openMocapDesktop', {
  isElectron: true,
  selectBlenderExe: () => ipcRenderer.invoke('desktop:select-blender'),
  openPath: (targetPath) => ipcRenderer.invoke('desktop:open-path', targetPath),
  openExternal: (url) => ipcRenderer.invoke('desktop:open-external', url),
  checkBackendHealth: () => ipcRenderer.invoke('desktop:backend-health'),
  getAppVersion: () => ipcRenderer.invoke('updater:get-version'),
  checkForUpdates: () => ipcRenderer.invoke('updater:check'),
  downloadUpdate: () => ipcRenderer.invoke('updater:download'),
  installUpdateNow: () => ipcRenderer.invoke('updater:install'),
  onUpdateStatus: (cb) => subscribe('updater:status', cb),
  onUpdateAvailable: (cb) => subscribe('updater:available', cb),
  onUpdateProgress: (cb) => subscribe('updater:progress', cb),
  onUpdateDownloaded: (cb) => subscribe('updater:downloaded', cb),
});
