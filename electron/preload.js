const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  /** Show a native OS desktop notification.
   * @param {{ title: string, body: string }} options
   */
  showNotification: (options) => {
    ipcRenderer.send('show-notification', options)
  },
})
