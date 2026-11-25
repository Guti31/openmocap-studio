const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const { autoUpdater } = require('electron-updater');
const { spawn, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const BACKEND_PORT = 8000;
const BACKEND_HOST = '127.0.0.1';
const HEALTH_URL = `http://${BACKEND_HOST}:${BACKEND_PORT}/api/health`;
const MAX_BACKEND_RESTARTS = 3;
const MAX_LOG_BYTES = 2 * 1024 * 1024;

let mainWindow = null;
let backendProcess = null;
let backendLogStream = null;
let restartCount = 0;
let isQuitting = false;
let updaterConfigured = false;

function normalizeReleaseNotes(notes) {
  if (!notes) return '';
  if (typeof notes === 'string') return notes.replace(/<[^>]+>/g, '').trim();
  if (Array.isArray(notes)) {
    return notes
      .map((entry) => {
        const ver = entry?.version ? `v${entry.version}: ` : '';
        const body = typeof entry?.note === 'string' ? entry.note.replace(/<[^>]+>/g, '').trim() : '';
        return `${ver}${body}`.trim();
      })
      .filter(Boolean)
      .join('\n\n');
  }
  return '';
}

function sendUpdateEvent(channel, payload) {
  if (mainWindow && !mainWindow.isDestroyed() && mainWindow.webContents) {
    mainWindow.webContents.send(channel, payload);
  }
}

function configureAutoUpdater() {
  if (updaterConfigured) return;
  updaterConfigured = true;

  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.allowPrerelease = false;

  autoUpdater.on('checking-for-update', () => {
    sendUpdateEvent('updater:status', {
      state: 'checking',
      currentVersion: app.getVersion(),
      message: 'Buscando actualizaciones en GitHub Releases...',
    });
  });

  autoUpdater.on('update-available', (info) => {
    const payload = {
      version: String(info?.version || ''),
      releaseName: String(info?.releaseName || `v${info?.version || ''}`),
      releaseDate: info?.releaseDate ? String(info.releaseDate) : '',
      releaseNotes: normalizeReleaseNotes(info?.releaseNotes),
      currentVersion: app.getVersion(),
    };
    sendUpdateEvent('updater:available', payload);
    sendUpdateEvent('updater:status', {
      state: 'available',
      currentVersion: app.getVersion(),
      version: payload.version,
      message: `Nueva versión v${payload.version} disponible.`,
    });
  });

  autoUpdater.on('update-not-available', (info) => {
    sendUpdateEvent('updater:status', {
      state: 'up-to-date',
      currentVersion: app.getVersion(),
      version: String(info?.version || app.getVersion()),
      message: `Ya cuentas con la última versión (v${app.getVersion()}).`,
    });
  });

  autoUpdater.on('download-progress', (progress) => {
    sendUpdateEvent('updater:progress', {
      percent: Number(progress?.percent || 0),
      transferred: Number(progress?.transferred || 0),
      total: Number(progress?.total || 0),
      bytesPerSecond: Number(progress?.bytesPerSecond || 0),
    });
  });

  autoUpdater.on('update-downloaded', (info) => {
    const payload = {
      version: String(info?.version || ''),
      releaseName: String(info?.releaseName || `v${info?.version || ''}`),
      releaseDate: info?.releaseDate ? String(info.releaseDate) : '',
      releaseNotes: normalizeReleaseNotes(info?.releaseNotes),
      currentVersion: app.getVersion(),
    };
    sendUpdateEvent('updater:downloaded', payload);
    sendUpdateEvent('updater:status', {
      state: 'downloaded',
      currentVersion: app.getVersion(),
      version: payload.version,
      message: `Versión v${payload.version} lista para instalar.`,
    });
  });

  autoUpdater.on('error', (err) => {
    sendUpdateEvent('updater:status', {
      state: 'error',
      currentVersion: app.getVersion(),
      message: err?.message ? String(err.message) : 'No se pudo comprobar actualizaciones.',
    });
  });
}

function getBackendLogPath() {
  return path.join(app.getPath('userData'), 'logs', 'backend.log');
}

function openBackendLogStream() {
  const logPath = getBackendLogPath();
  try {
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    if (fs.existsSync(logPath) && fs.statSync(logPath).size > MAX_LOG_BYTES) {
      const rotated = `${logPath}.1`;
      try {
        if (fs.existsSync(rotated)) fs.unlinkSync(rotated);
        fs.renameSync(logPath, rotated);
      } catch {
        // Ignorar fallo de rotación si el archivo está bloqueado
      }
    }
    if (backendLogStream) {
      backendLogStream.end();
      backendLogStream = null;
    }
    backendLogStream = fs.createWriteStream(logPath, { flags: 'a' });
  } catch {
    backendLogStream = null;
  }
  return backendLogStream;
}

function closeBackendLogStream() {
  if (backendLogStream) {
    try {
      backendLogStream.end();
    } catch {
      // Ignorar
    }
    backendLogStream = null;
  }
}

function checkHealthOnce() {
  return new Promise((resolve) => {
    const req = http.get(HEALTH_URL, (res) => {
      resolve(res.statusCode === 200);
      res.resume();
    });
    req.on('error', () => resolve(false));
    req.setTimeout(800, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForBackend(timeoutMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await checkHealthOnce()) {
      restartCount = 0;
      return true;
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  return false;
}

async function startBackendIfNeeded() {
  if (await checkHealthOnce()) {
    restartCount = 0;
    return;
  }

  const isPackaged = app.isPackaged;
  const projectRoot = path.resolve(__dirname, '..', '..');

  if (isPackaged) {
    const exeName = process.platform === 'win32' ? 'openmocap-backend.exe' : 'openmocap-backend';
    const backendExe = path.join(process.resourcesPath, 'backend', exeName);
    if (!fs.existsSync(backendExe)) {
      dialog.showErrorBox(
        'OpenMocap Studio - Error de inicio',
        `No se encontró el motor del servidor en:\n${backendExe}\n\nReinstala la aplicación para restaurar los archivos del backend.`
      );
      return;
    }
    backendProcess = spawn(backendExe, ['--host', BACKEND_HOST, '--port', String(BACKEND_PORT)], {
      cwd: path.dirname(backendExe),
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } else {
    const venvPy = path.join(projectRoot, 'backend', '.venv', 'Scripts', 'python.exe');
    const pythonCmd = fs.existsSync(venvPy) ? venvPy : 'python';
    backendProcess = spawn(
      pythonCmd,
      ['-m', 'backend.main', '--host', BACKEND_HOST, '--port', String(BACKEND_PORT)],
      {
        cwd: projectRoot,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
      }
    );
  }

  if (backendProcess) {
    const logStream = openBackendLogStream();
    const writeLog = (prefix, chunk) => {
      if (logStream && !logStream.destroyed) {
        logStream.write(`[${new Date().toISOString()}][${prefix}] ${chunk.toString()}`);
      }
    };
    if (backendProcess.stdout) {
      backendProcess.stdout.on('data', (chunk) => writeLog('OUT', chunk));
    }
    if (backendProcess.stderr) {
      backendProcess.stderr.on('data', (chunk) => writeLog('ERR', chunk));
    }
    backendProcess.on('error', (err) => {
      writeLog('SPAWN_ERR', err?.message || String(err));
    });
    backendProcess.on('exit', (code) => {
      writeLog('EXIT', `code=${code}\n`);
      backendProcess = null;
      if (!isQuitting) {
        restartCount += 1;
        if (restartCount <= MAX_BACKEND_RESTARTS) {
          setTimeout(() => {
            startBackendIfNeeded().catch(() => {});
          }, 1500);
        } else {
          dialog.showErrorBox(
            'OpenMocap Studio - Servidor detenido',
            `El motor backend se cerró inesperadamente tras ${MAX_BACKEND_RESTARTS} reintentos.\nRevisa el registro en:\n${getBackendLogPath()}`
          );
        }
      }
    });
  }

  await waitForBackend(20000);
}

function stopBackendProcess() {
  isQuitting = true;
  closeBackendLogStream();
  if (!backendProcess || !backendProcess.pid) return;
  const pid = backendProcess.pid;
  try {
    if (process.platform === 'win32') {
      execSync(`taskkill /PID ${pid} /T /F`, { stdio: 'ignore' });
    } else {
      backendProcess.kill('SIGTERM');
    }
  } catch {
    // Proceso ya cerrado
  }
  backendProcess = null;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1480,
    height: 920,
    minWidth: 1200,
    minHeight: 740,
    backgroundColor: '#0b0f17',
    title: 'OpenMocap Studio - APLICACION_TRAJE',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  if (process.env.VITE_DEV_SERVER_URL || !app.isPackaged) {
    const devUrl = process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173';
    mainWindow.loadURL(devUrl).catch(() => {
      mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
    });
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

ipcMain.handle('desktop:select-blender', async () => {
  const res = await dialog.showOpenDialog(mainWindow, {
    title: 'Seleccionar ejecutable de Blender',
    properties: ['openFile'],
    filters: [
      { name: 'Blender', extensions: process.platform === 'win32' ? ['exe'] : ['*'] },
    ],
  });
  if (res.canceled || !res.filePaths.length) return null;
  return res.filePaths[0];
});

ipcMain.handle('desktop:open-path', async (_evt, targetPath) => {
  if (!targetPath) return false;
  await shell.openPath(targetPath);
  return true;
});

ipcMain.handle('desktop:backend-health', async () => {
  return await checkHealthOnce();
});

ipcMain.handle('desktop:open-external', async (_evt, rawUrl) => {
  if (typeof rawUrl !== 'string' || !/^https?:\/\//i.test(rawUrl)) return false;
  await shell.openExternal(rawUrl);
  return true;
});

ipcMain.handle('updater:get-version', () => app.getVersion());

ipcMain.handle('updater:check', async () => {
  const currentVersion = app.getVersion();
  if (!app.isPackaged) {
    const statusPayload = {
      state: 'up-to-date',
      currentVersion,
      version: currentVersion,
      devMode: true,
      message: `Modo desarrollo activo (v${currentVersion}). Las auto-actualizaciones se ejecutan en el instalador empaquetado.`,
    };
    sendUpdateEvent('updater:status', statusPayload);
    return { ok: true, devMode: true, currentVersion };
  }
  configureAutoUpdater();
  try {
    const res = await autoUpdater.checkForUpdates();
    return { ok: true, currentVersion, version: res?.updateInfo?.version || currentVersion };
  } catch (err) {
    const msg = err?.message ? String(err.message) : 'Error consultando actualizaciones.';
    sendUpdateEvent('updater:status', { state: 'error', currentVersion, message: msg });
    return { ok: false, currentVersion, message: msg };
  }
});

ipcMain.handle('updater:download', async () => {
  if (!app.isPackaged) return { ok: false, message: 'No disponible en modo desarrollo.' };
  configureAutoUpdater();
  try {
    await autoUpdater.downloadUpdate();
    return { ok: true };
  } catch (err) {
    const msg = err?.message ? String(err.message) : 'Error descargando la actualización.';
    sendUpdateEvent('updater:status', { state: 'error', currentVersion: app.getVersion(), message: msg });
    return { ok: false, message: msg };
  }
});

ipcMain.handle('updater:install', async () => {
  stopBackendProcess();
  if (app.isPackaged) {
    setImmediate(() => {
      autoUpdater.quitAndInstall(false, true);
    });
  }
  return { ok: true };
});

app.whenReady().then(async () => {
  configureAutoUpdater();
  await startBackendIfNeeded();
  createWindow();

  if (app.isPackaged) {
    setTimeout(() => {
      autoUpdater.checkForUpdates().catch(() => {});
    }, 4000);
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('before-quit', () => {
  stopBackendProcess();
});

app.on('window-all-closed', () => {
  stopBackendProcess();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

