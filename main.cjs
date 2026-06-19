const { app, BrowserWindow, Tray, Menu, nativeImage, Notification, ipcMain } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const net = require('net')
const fs = require('fs')

// ── Filter known-harmless libpng warnings from Electron's internal PNGs ─
const origWrite = process.stderr.write.bind(process.stderr)
process.stderr.write = (chunk, encoding, callback) => {
  const str = chunk.toString()
  if (str.includes('libpng warning: iCCP: known incorrect sRGB profile')) {
    if (typeof callback === 'function') callback()
    return true
  }
  return origWrite(chunk, encoding, callback)
}

// ── Detect environment ──────────────────────────────────────────────
const DEV = process.env.NODE_ENV === 'development' || process.argv.includes('--dev')
const PACKAGED = app.isPackaged  // true when built by electron-builder
const PORT = parseInt(process.env.HYPERAGENT_PORT, 10) || 18080
const VITE_DEV_PORTS = [5174, 5175, 5176, 5177, 5178]
const CHECK_HOSTS = ['127.0.0.1', '::1']
const IS_WINDOWS = process.platform === 'win32'

const REPO_ROOT = path.resolve(__dirname, '..')

// Force userData to a consistent location so packaged builds don't pick
// the wrong path based on package.json "name" ("frontend" → %APPDATA%/frontend).
app.setPath('userData', path.join(app.getPath('appData'), 'HyperAgent'))

// ── Child processes ─────────────────────────────────────────────────
/** @type {import('child_process').ChildProcess[]} */
const children = []

function findBackendExe() {
  if (PACKAGED) {
    // electron-builder puts extraResources into process.resourcesPath
    return path.join(process.resourcesPath, 'backend', 'hyperagent-backend.exe')
  }
  // Development: look in the project's dist/ folder
  const local = path.join(REPO_ROOT, 'dist', 'hyperagent-backend.exe')
  if (fs.existsSync(local)) return local
  return null
}

function spawnBackend() {
  let cmd, args, cwd

  const backendExe = findBackendExe()
  if (PACKAGED && backendExe && fs.existsSync(backendExe)) {
    // ── Production mode: bundled backend executable ──
    console.log(`[electron] Starting bundled backend: ${backendExe}`)
    cmd = backendExe
    args = []
    cwd = path.dirname(backendExe)
  } else {
    // ── Development mode: uv run uvicorn ──
    cmd = 'uv'
    args = ['run', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', String(PORT)]
    cwd = REPO_ROOT
    console.log(`[electron] Starting backend via: ${cmd} ${args.join(' ')}`)
  }

  const proc = spawn(cmd, args, {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: IS_WINDOWS && !PACKAGED,
    env: {
      ...process.env,
      HYPERAGENT_PORT: String(PORT),
      HYPERAGENT_HOST: '127.0.0.1',
      // In packaged mode, store data in the user's app data directory so it
      // survives version updates.  Dev mode uses the default ./data/ path.
      ...(PACKAGED ? { HYPERAGENT_DATA_DIR: app.getPath('userData') } : {}),
    },
  })

  proc.stdout.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`)
  })

  proc.stderr.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`)
  })

  proc.on('error', (err) => {
    console.error('[backend] Failed to start:', err.message)
  })

  proc.on('exit', (code) => {
    console.log(`[backend] Exited with code ${code}`)
  })

  children.push(proc)
  return proc
}

function killAllChildren() {
  for (const proc of children) {
    if (proc && !proc.killed) {
      try { proc.kill('SIGTERM') } catch { proc.kill() }
    }
  }
}

// ── TCP port check (more reliable than http.get on Windows) ────────────
function checkPort(host, port) {
  return new Promise((resolve) => {
    const socket = new net.Socket()
    socket.setTimeout(2000)
    socket.on('connect', () => { socket.destroy(); resolve(true) })
    socket.on('error', () => { socket.destroy(); resolve(false) })
    socket.on('timeout', () => { socket.destroy(); resolve(false) })
    socket.connect(port, host)
  })
}

function waitForPort(hosts, port, retries = 30, interval = 500) {
  return new Promise((resolve, reject) => {
    const check = async (attempt) => {
      for (const host of hosts) {
        if (await checkPort(host, port)) { resolve(host); return }
      }
      if (attempt >= retries) {
        reject(new Error(`Port ${port} not open after ${retries} retries (${Math.round(retries * interval / 1000)}s)`))
      } else {
        setTimeout(() => check(attempt + 1), interval)
      }
    }
    check(0)
  })
}

// ── Find active Vite dev port ─────────────────────────────────────────
async function findVitePort() {
  for (const port of VITE_DEV_PORTS) {
    for (const host of CHECK_HOSTS) {
      if (await checkPort(host, port)) {
        console.log(`[electron] Found Vite dev server on ${host}:${port}`)
        return port
      }
    }
  }
  console.warn('[electron] No Vite dev server found, trying default port')
  return VITE_DEV_PORTS[0]
}

// ── Window ─────────────────────────────────────────────────────────────
/** @type {BrowserWindow | null} */
let mainWindow = null
/** @type {Tray | null} */
let tray = null

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200, height: 800, minWidth: 800, minHeight: 600,
    title: 'HyperAgent',
    icon: (() => {
      const ico = path.join(__dirname, 'icon.ico')
      const png = path.join(__dirname, 'icon.png')
      if (fs.existsSync(ico)) return ico
      return png
    })(),
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,  // don't suspend timers when minimized
    },
    show: false,
  })

  // Dev or production URL
  if (DEV) {
    const vitePort = global.__vitePort || VITE_DEV_PORTS[0]
    mainWindow.loadURL(`http://localhost:${vitePort}`)
  } else {
    mainWindow.loadURL(`http://localhost:${PORT}`)
  }

  mainWindow.once('ready-to-show', () => { mainWindow.show() })

  // Minimize to tray instead of closing
  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault()
      mainWindow.hide()
    }
  })

  // Log state changes to diagnose tray hide/show issues
  mainWindow.on('show', () => {
    console.log('[electron] Window shown (backend still running?)')
  })
  mainWindow.on('hide', () => {
    console.log('[electron] Window hidden to tray')
  })

  mainWindow.on('closed', () => { mainWindow = null })
}

// ── Tray ───────────────────────────────────────────────────────────────
function createTray() {
  const iconPath = path.join(__dirname, 'tray-icon.png')
  let nativeIcon

  if (fs.existsSync(iconPath)) {
    nativeIcon = nativeImage.createFromPath(iconPath)
  } else {
    nativeIcon = nativeImage.createEmpty()
  }

  if (process.platform === 'darwin') {
    nativeIcon = nativeIcon.resize({ width: 16, height: 16 })
  }

  tray = new Tray(nativeIcon)

  const template = [
    {
      label: '显示 HyperAgent',
      click: () => {
        if (mainWindow) { mainWindow.show(); mainWindow.focus() }
      },
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        app.isQuitting = true
        killAllChildren()
        app.quit()
      },
    },
  ]

  const contextMenu = Menu.buildFromTemplate(template)
  tray.setToolTip('HyperAgent - 个人 AI 助手')
  tray.setContextMenu(contextMenu)

  tray.on('double-click', () => {
    if (mainWindow) { mainWindow.show(); mainWindow.focus() }
  })
}

// ── IPC: Native notifications ─────────────────────────────────────────
ipcMain.on('show-notification', (_event, { title, body }) => {
  if (Notification.isSupported()) {
    const notif = new Notification({ title, body })
    notif.show()
    notif.on('click', () => {
      if (mainWindow) { mainWindow.show(); mainWindow.focus() }
    })
  }
})

// ── App lifecycle ──────────────────────────────────────────────────────
// Prevent multiple instances (double-clicking the exe while running)
const gotTheLock = app.requestSingleInstanceLock()
if (!gotTheLock) {
  console.log('[electron] Another instance is running, quitting.')
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.show()
      mainWindow.focus()
    }
  })
}

app.whenReady().then(async () => {
  // 1. Start backend
  spawnBackend()

  // 2. Wait for backend to be ready (TCP port check, no HTTP dependency)
  try {
    const host = await waitForPort(CHECK_HOSTS, PORT, 60, 500)
    console.log(`[electron] Backend is ready on ${host}:${PORT}`)
  } catch (err) {
    console.error('[electron] Backend failed to start:', err.message)
  }

  // 3. Detect Vite dev port (dev mode only)
  if (DEV) {
    global.__vitePort = await findVitePort()
  }

  // 4. Create window and tray
  createWindow()
  createTray()
})

app.on('window-all-closed', () => {
  // On Windows, we keep the app running in the tray
})

app.on('before-quit', () => {
  app.isQuitting = true
  killAllChildren()
})

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow()
  } else {
    mainWindow.show()
  }
})
