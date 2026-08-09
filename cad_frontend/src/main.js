import {
  AcApDocManager,
  AcApOpenViewMode,
  AcEdOpenMode,
  applyUiTheme
} from '@mlightcad/cad-simple-viewer'
import {
  SIMPLE_UI_PLUGIN_NAME,
  toolbarPreset
} from '@mlightcad/cad-simple-ui-plugin'
import { registerSimpleUiPlugin } from '@mlightcad/cad-simple-ui-plugin/register'
import { Box3, Vector3 } from 'three'

import './viewer.css'

const root = document.getElementById('cad-viewer')

function setStatus(message, state = 'loading') {
  const status = document.getElementById('cad-viewer-status')
  if (!status) return
  status.dataset.state = state
  status.querySelector('[data-status-message]').textContent = message
  status.hidden = state === 'ready'
}

function setNotice(message) {
  const notice = document.getElementById('cad-viewer-notice')
  if (!notice) return
  notice.textContent = message
  notice.hidden = !message
}

function quantile(values, ratio) {
  if (!values.length) return 0
  const sorted = [...values].sort((left, right) => left - right)
  const position = (sorted.length - 1) * ratio
  const lower = Math.floor(position)
  const fraction = position - lower
  return sorted[lower + 1] === undefined
    ? sorted[lower]
    : sorted[lower] + fraction * (sorted[lower + 1] - sorted[lower])
}

function collectGeometryBounds(view) {
  const scene = view._scene?.internalScene
  if (!scene) return []
  scene.updateMatrixWorld(true)
  const entries = []
  scene.traverse(object => {
    if (!object.visible || !object.geometry) return
    if (!object.geometry.boundingBox) object.geometry.computeBoundingBox?.()
    if (!object.geometry.boundingBox) return
    const bounds = object.geometry.boundingBox.clone().applyMatrix4(object.matrixWorld)
    const values = [bounds.min.x, bounds.min.y, bounds.max.x, bounds.max.y]
    if (!bounds.isEmpty() && values.every(Number.isFinite)) {
      entries.push({ bounds, name: object.name || '', type: object.type || '' })
    }
  })
  return entries
}

function practicalGeometryBounds(geometryEntries, database) {
  if (!database?.extmin || !database?.extmax) return null
  const boxes = geometryEntries.map(entry => entry.bounds)
  if (boxes.length < 5) return null

  const centers = boxes.map(bounds => bounds.getCenter(new Vector3()))
  const xs = centers.map(point => point.x)
  const ys = centers.map(point => point.y)
  const xQ1 = quantile(xs, 0.25)
  const xQ3 = quantile(xs, 0.75)
  const yQ1 = quantile(ys, 0.25)
  const yQ3 = quantile(ys, 0.75)
  const xMargin = Math.max((xQ3 - xQ1) * 4, 1000)
  const yMargin = Math.max((yQ3 - yQ1) * 4, 1000)
  const inliers = boxes.filter((bounds, index) => {
    const center = centers[index]
    return center.x >= xQ1 - xMargin && center.x <= xQ3 + xMargin &&
      center.y >= yQ1 - yMargin && center.y <= yQ3 + yMargin
  })
  if (inliers.length < Math.max(3, boxes.length * 0.5)) return null

  const practical = new Box3()
  inliers.forEach(bounds => practical.union(bounds))
  const databaseBounds = new Box3(database.extmin.clone(), database.extmax.clone())
  const practicalSize = practical.getSize(new Vector3())
  const databaseSize = databaseBounds.getSize(new Vector3())
  const practicalDiagonal = Math.hypot(practicalSize.x, practicalSize.y)
  const databaseDiagonal = Math.hypot(databaseSize.x, databaseSize.y)
  if (!practicalDiagonal || databaseDiagonal <= practicalDiagonal * 25) return null
  return { bounds: practical, totalObjects: boxes.length, includedObjects: inliers.length }
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
        openViewMode: AcApOpenViewMode.Extents,
        progressiveRendering: true,
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
      openViewMode: AcApOpenViewMode.Extents,
      progressiveRendering: true,
      sysVars: { lwdisplay: false }
    })
    const view = AcApDocManager.instance.curView
    if (!opened && !view) throw new Error('The drawing could not be decoded.')

    setStatus('Fitting the drawing to the available view...')
    if (view) {
      view.backgroundColor = 0xffffff
      view.zoomToFitDrawing(30000)
      const processingDeadline = Date.now() + 30000
      let stableChecks = 0
      while (Date.now() < processingDeadline && stableChecks < 5) {
        await new Promise(resolve => window.setTimeout(resolve, 150))
        stableChecks = view.isProcessingEntities ? 0 : stableChecks + 1
      }
      const database = AcApDocManager.instance.curDocument?.database
      // Some production DWGs contain stray entities at extreme coordinates. Their
      // database extents make an ordinary zoom-to-fit look blank, so derive a
      // majority-cluster fallback from the geometry the pinned viewer rendered.
      const geometryEntries = collectGeometryBounds(view)
      const practicalFit = practicalGeometryBounds(geometryEntries, database)
      const fit = () => {
        if (practicalFit) view.zoomTo(practicalFit.bounds)
        else view.zoomToFitDrawing(5000)
        view.isDirty = true
      }
      fit()
      const refit = () => {
        fit()
      }
      window.setTimeout(refit, 1000)
      window.setTimeout(refit, 3000)
      new ResizeObserver(refit).observe(root)
      const missedData = view.missedData
      if (missedData.xrefs?.length) {
        setNotice(
          `${missedData.xrefs.length} external drawing reference(s) are not embedded in this file. ` +
          'The available geometry is shown; upload the referenced DWG files if any areas are missing.'
        )
      }
      // Query-scoped diagnostics help support real-world DWGs without logging drawing data.
      if (new URLSearchParams(window.location.search).has('cad_debug')) {
        const point = value => value ? { x: value.x, y: value.y, z: value.z } : null
        root.dataset.cadDebug = JSON.stringify({
          extmin: point(database?.extmin),
          extmax: point(database?.extmax),
          currentSpaceId: String(database?.currentSpaceId || ''),
          modelSpaceId: String(database?.tables?.blockTable?.modelSpace?.objectId || ''),
          center: point(view.center),
          missingFontCount: missedData.fonts?.size || 0,
          missingImageCount: missedData.images?.size || 0,
          unresolvedXrefs: missedData.xrefs?.slice(0, 20) || [],
          unresolvedXrefCount: missedData.xrefs?.length || 0,
          processing: view.isProcessingEntities,
          sceneChildren: view._scene?.internalScene?.children?.length || 0,
          practicalFit: practicalFit ? {
            min: point(practicalFit.bounds.min), max: point(practicalFit.bounds.max),
            totalObjects: practicalFit.totalObjects,
            includedObjects: practicalFit.includedObjects
          } : null,
          geometryCount: geometryEntries.length,
          geometryBounds: geometryEntries.slice(0, 40).map(entry => ({
            name: entry.name, type: entry.type,
            min: point(entry.bounds.min), max: point(entry.bounds.max)
          }))
        })
      }
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
