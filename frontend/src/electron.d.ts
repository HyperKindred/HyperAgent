/** Type declarations for Electron preload API exposed via contextBridge. */

interface ElectronAPI {
  showNotification: (options: { title: string; body: string }) => void
}

interface Window {
  electronAPI?: ElectronAPI
}
