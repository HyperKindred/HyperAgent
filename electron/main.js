const { app, BrowserWindow, Tray, Menu, nativeImage, Notification, ipcMain } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const http = require('http')

// ── Configuration ──────────────────────────────────────────────────────
const DEV = process.env.NODE_ENV === 'development' || process.argv.includes('--dev')
const PORT = 8000
const VITE_DEV_PORTS = [5174, 5175, 5176, 5177, 5178]
const IS_WINDOWS = process.platform === 'win32'

const REPO_ROOT = path.resolve(__dirname, '..')
const BACKEND_DIR = REPO_ROOT

// ── Child processes ────────────────────────────────────────────────────
/** @type {import('child_process').ChildProcess[]} */
const children = []

function spawnBackend() {
  const cmd = IS_WINDOWS ? 'uv' : 'uv'
  const args = ['run', 'uvicorn', 'app.main:app', '--port', String(PORT), '--reload']

  const proc = spawn(cmd, args, {
    cwd: BACKEND_DIR,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: IS_WINDOWS,
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

// ── Backend health check ───────────────────────────────────────────────
function waitForBackend(retries = 60, interval = 500) {
  return new Promise((resolve, reject) => {
    const check = (attempt) => {
      const req = http.get(`http://localhost:${PORT}/api/health`, (res) => {
        // Any response (even 404) means the server is up
        resolve()
      })
      req.on('error', () => {
        if (attempt >= retries) {
          reject(new Error(`Backend not ready after ${retries} retries (${Math.round(retries * interval / 1000)}s)`))
        } else {
          setTimeout(() => check(attempt + 1), interval)
        }
      })
      req.end()
    }
    check(0)
  })
}

// ── Find active Vite dev port ─────────────────────────────────────────
function findVitePort() {
  return new Promise((resolve) => {
    let idx = 0
    const tryNext = () => {
      if (idx >= VITE_DEV_PORTS.length) {
        console.warn('[electron] No Vite dev server found, trying default port')
        resolve(VITE_DEV_PORTS[0])
        return
      }
      const p = VITE_DEV_PORTS[idx]
      const req = http.get(`http://localhost:${p}`, (res) => {
        res.resume()
        console.log(`[electron] Found Vite dev server on port ${p}`)
        resolve(p)
      })
      req.on('error', () => {
        idx++
        tryNext()
      })
      req.end()
    }
    tryNext()
  })
}

// ── Window ─────────────────────────────────────────────────────────────
/** @type {BrowserWindow | null} */
let mainWindow = null
/** @type {Tray | null} */
let tray = null

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: 'HyperAgent',
    icon: (() => {
      const ico = path.join(REPO_ROOT, 'electron', 'icon.ico')
      const png = path.join(REPO_ROOT, 'electron', 'icon.png')
      try { if (require('fs').existsSync(ico)) return ico } catch {}
      return png
    })(),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    show: false, // show after ready
  })

  // Dev or production URL
  if (DEV) {
    // Vite port is set before createWindow() is called
    const vitePort = global.__vitePort || VITE_DEV_PORTS[0]
    mainWindow.loadURL(`http://localhost:${vitePort}`)
    // DevTools: press F12 to open, not auto-open
  } else {
    mainWindow.loadURL(`http://localhost:${PORT}`)
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  // Minimize to tray instead of closing
  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault()
      mainWindow.hide()
    }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// ── Tray ───────────────────────────────────────────────────────────────
function createTray() {
  const iconPath = path.join(REPO_ROOT, 'electron', 'tray-icon.png')
  const fs = require('fs')
  let nativeIcon

  if (fs.existsSync(iconPath)) {
    nativeIcon = nativeImage.createFromPath(iconPath)
  } else {
    nativeIcon = nativeImage.createEmpty()
  }

  // macOS: resize to 16x16 for menu bar. Windows loads the 32x32 tray icon
  // directly — it's already at a size close to the tray display area.
  if (process.platform === 'darwin') {
    nativeIcon = nativeIcon.resize({ width: 16, height: 16 })
  }

  tray = new Tray(nativeIcon)

  const template = [
    {
      label: '显示 HyperAgent',
      click: () => {
        if (mainWindow) {
          mainWindow.show()
          mainWindow.focus()
        }
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
    if (mainWindow) {
      mainWindow.show()
      mainWindow.focus()
    }
  })
}

// ── IPC: Native notifications ─────────────────────────────────────────
ipcMain.on('show-notification', (_event, { title, body }) => {
  if (Notification.isSupported()) {
    const notif = new Notification({ title, body })
    notif.show()
    notif.on('click', () => {
      if (mainWindow) {
        mainWindow.show()
        mainWindow.focus()
      }
    })
  }
})

	// ── App lifecycle ──────────────────────────────────────────────────────
app.whenReady().then(async () => {
  // 1. Start backend
  spawnBackend()

  // 2. Wait for backend to be ready
  try {
    await waitForBackend()
    console.log('[electron] Backend is ready')
  } catch (err) {
    console.error('[electron] Backend failed to start:', err.message)
    // Continue anyway — the window will show an error message
  }

  // 3. Detect Vite dev port (dev mode only)
  if (DEV) {
    const vitePort = await findVitePort()
    global.__vitePort = vitePort
  }

  // 4. Create window and tray
  createWindow()
  createTray()
})

app.on('window-all-closed', () => {
  // On Windows, we keep the app running in the tray
  // Only quit if explicitly told to
})

app.on('before-quit', () => {
  app.isQuitting = true
  killAllChildren()
})

app.on('activate', () => {
  // macOS: re-create window when dock icon is clicked
  if (mainWindow === null) {
    createWindow()
  } else {
    mainWindow.show()
  }
})
