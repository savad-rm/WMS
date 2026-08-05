import {
  AcApDocManager,
  AcEdOpenMode,
  applyUiTheme
} from '@mlightcad/cad-simple-viewer'
import {
  SIMPLE_UI_PLUGIN_NAME,
  toolbarPreset
} from '@mlightcad/cad-simple-ui-plugin'
import { registerSimpleUiPlugin } from '@mlightcad/cad-simple-ui-plugin/register'

import './viewer.css'

const root = document.getElementById('cad-viewer')

function setStatus(message, state = 'loading') {
  const status = document.getElementById('cad-viewer-status')
  if (!status) return
  status.dataset.state = state
  status.querySelector('[data-status-message]').textContent = message
  status.hidden = state === 'ready'
}

async function startViewer() {
  if (!root) return

  const fileUrl = root.dataset.fileUrl
  const fileName = root.dataset.fileName || 'CAD drawing'
  if (!fileUrl) {
    setStatus('The drawing URL is missing.', 'error')
    return
  }

  try {
    // Most architectural drawings use black/true-colour linework. A light canvas
    // keeps those entities visible instead of presenting an apparently blank view.
    applyUiTheme('light', root)
    AcApDocManager.createInstance({
      container: root,
      busyIndicatorHost: root,
      autoResize: true,
      baseUrl: '/static/cad_viewer/',
      checkWorkersOnInit: true,
      openDocumentDefaults: {
        minimumChunkSize: 1000,
        mode: AcEdOpenMode.Read,
        sysVars: { lwdisplay: false }
      },
      webworkerFileUrls: {
        mtextRender: '/static/cad_viewer/workers/mtext-renderer-worker.js',
        dxfParser: '/static/cad_viewer/workers/dxf-parser-worker.js',
        dwgParser: '/static/cad_viewer/workers/libredwg-parser-worker.js'
      }
    })

    const workersReady = await AcApDocManager.instance.areWorkersReady()
    if (!workersReady) {
      throw new Error('The local CAD processing files are unavailable.')
    }

    await registerSimpleUiPlugin(AcApDocManager.instance.pluginManager, {
      host: root,
      dockPanel: {
        defaultSide: 'left',
        defaultOpen: false,
        defaultWidth: 280
      },
      toolbar: {
        placement: 'right',
        items: [],
        collapsible: true
      }
    })

    const plugin = AcApDocManager.instance.pluginManager.getPlugin(SIMPLE_UI_PLUGIN_NAME)
    plugin.setToolbarItems([
      toolbarPreset('select'),
      toolbarPreset('pan'),
      toolbarPreset('zoom-extent'),
      toolbarPreset('zoom-window'),
      toolbarPreset('layer'),
      toolbarPreset('measure'),
      toolbarPreset('switch-bg')
    ])

    setStatus(`Loading ${fileName}…`)
    const response = await fetch(fileUrl, {
      credentials: 'same-origin',
      headers: { Accept: 'application/octet-stream' }
    })
    if (!response.ok) {
      throw new Error(`The drawing could not be downloaded (${response.status}).`)
    }
    const fileContent = await response.arrayBuffer()
    const opened = await AcApDocManager.instance.openDocument(fileName, fileContent, {
      minimumChunkSize: 1000,
      mode: AcEdOpenMode.Read,
      sysVars: { lwdisplay: false }
    })
    const view = AcApDocManager.instance.curView
    if (!opened && !view) throw new Error('The drawing could not be decoded.')

    setStatus('Fitting the drawing to the available view...')
    if (view) {
      view.backgroundColor = 0xffffff
      const processingDeadline = Date.now() + 10000
      while (view.isProcessingEntities && Date.now() < processingDeadline) {
        await new Promise(resolve => window.setTimeout(resolve, 100))
      }
      view.zoomToFitDrawing(5000)
      view.isDirty = true
    }

    setStatus('', 'ready')
  } catch (error) {
    console.error('WMS CAD viewer failed:', error)
    setStatus(
      'This drawing could not be displayed. It may use an unsupported DWG entity or be damaged. You can still download the original file.',
      'error'
    )
  }
}

void startViewer()
