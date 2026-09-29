import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import { Document, Page } from 'react-pdf'
import { X, ChevronLeft, ChevronRight, Download, Loader2, FileText } from 'lucide-react'
import '../lib/pdfConfig'

interface PdfZoomModalProps {
  url: string
  filename?: string | null
  onClose: () => void
}

interface ZoomPosition {
  x: number // 0-1 relative position
  y: number // 0-1 relative position
}

export default function PdfZoomModal({ url, filename, onClose }: PdfZoomModalProps) {
  const [numPages, setNumPages] = useState<number>(0)
  const [currentPage, setCurrentPage] = useState<number>(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [zoomPosition, setZoomPosition] = useState<ZoomPosition | null>(null)
  const [pageDimensions, setPageDimensions] = useState<{ width: number; height: number } | null>(null)
  const [blobUrl, setBlobUrl] = useState<string | null>(null)

  const pageContainerRef = useRef<HTMLDivElement>(null)
  const blobUrlRef = useRef<string | null>(null)

  // Fetch PDF as blob to avoid CORS issues with PDF.js worker
  useEffect(() => {
    let isMounted = true

    const fetchPdf = async () => {
      try {
        const response = await fetch(url)
        if (!response.ok) throw new Error('PDF fetch failed')
        const blob = await response.blob()
        const objectUrl = URL.createObjectURL(blob)

        if (isMounted) {
          blobUrlRef.current = objectUrl
          setBlobUrl(objectUrl)
        } else {
          URL.revokeObjectURL(objectUrl)
        }
      } catch (err) {
        console.error('PDF fetch error:', err)
        if (isMounted) {
          setError('PDF konnte nicht geladen werden')
          setLoading(false)
        }
      }
    }
    fetchPdf()

    // Cleanup blob URL on unmount
    return () => {
      isMounted = false
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current)
        blobUrlRef.current = null
      }
    }
  }, [url])

  // Memoize options to prevent unnecessary reloads
  const documentOptions = useMemo(() => ({
    cMapUrl: `https://unpkg.com/pdfjs-dist@4.8.69/cmaps/`,
    cMapPacked: true,
  }), [])

  const handleDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages)
    setLoading(false)
  }

  const handleDocumentLoadError = (error: Error) => {
    console.error('PDF load error:', error)
    setError('PDF konnte nicht geladen werden')
    setLoading(false)
  }

  const onPageLoadSuccess = useCallback((page: { width: number; height: number }) => {
    setPageDimensions({ width: page.width, height: page.height })
  }, [])

  // Handle mouse move for hover zoom
  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height
    setZoomPosition({ x, y })
  }

  const handleMouseLeave = () => {
    setZoomPosition(null)
  }

  const goToPrevPage = () => {
    setCurrentPage((prev) => Math.max(1, prev - 1))
    setZoomPosition(null)
  }

  const goToNextPage = () => {
    setCurrentPage((prev) => Math.min(numPages, prev + 1))
    setZoomPosition(null)
  }

  const handleDownload = () => {
    const link = document.createElement('a')
    link.href = url
    link.download = filename || 'document.pdf'
    link.target = '_blank'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  // Calculate zoom view - larger size
  const zoomScale = 3
  const pdfWidth = 400
  const zoomViewSize = 500

  return (
    <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-[60] p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-7xl max-h-[95vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b bg-gray-50 rounded-t-xl">
          <h2 className="text-lg font-semibold text-gray-900 truncate">
            {filename || 'PDF Vorschau'}
          </h2>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden p-4">
          {loading && !blobUrl && (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="h-12 w-12 animate-spin text-gray-400" />
            </div>
          )}

          {error && (
            <div className="flex flex-col items-center justify-center h-full text-gray-500">
              <FileText className="h-16 w-16 mb-4" />
              <span className="text-lg">{error}</span>
            </div>
          )}

          {blobUrl && !error && (
            <div className="flex gap-6 h-full justify-center items-start">
              {/* Left: PDF Page */}
              <div className="flex flex-col items-center flex-shrink-0">
                <div className="text-sm text-gray-500 mb-2">
                  Maus über das Dokument bewegen
                </div>
                <div
                  ref={pageContainerRef}
                  className="border rounded-lg overflow-hidden bg-white cursor-crosshair"
                  onMouseMove={handleMouseMove}
                  onMouseLeave={handleMouseLeave}
                >
                  <Document
                    file={blobUrl}
                    onLoadSuccess={handleDocumentLoadSuccess}
                    onLoadError={handleDocumentLoadError}
                    loading={null}
                    options={documentOptions}
                  >
                    <Page
                      pageNumber={currentPage}
                      width={pdfWidth}
                      renderTextLayer={false}
                      renderAnnotationLayer={false}
                      onLoadSuccess={onPageLoadSuccess}
                      canvasBackground="white"
                    />
                  </Document>
                </div>
              </div>

              {/* Right: Zoom View */}
              <div className="flex flex-col items-center flex-shrink-0">
                <div className="text-sm text-gray-500 mb-2">
                  Vergrößerung ({zoomScale}x)
                </div>
                <div
                  className="border rounded-lg bg-gray-50 overflow-hidden"
                  style={{ width: zoomViewSize, height: zoomViewSize }}
                >
                  {zoomPosition && pageDimensions ? (
                    <div
                      className="relative"
                      style={{
                        width: zoomViewSize,
                        height: zoomViewSize,
                        overflow: 'hidden',
                      }}
                    >
                      <div
                        style={{
                          position: 'absolute',
                          left: -(zoomPosition.x * pdfWidth * zoomScale - zoomViewSize / 2),
                          top: -(zoomPosition.y * (pdfWidth * pageDimensions.height / pageDimensions.width) * zoomScale - zoomViewSize / 2),
                        }}
                      >
                        <Document
                          file={blobUrl}
                          loading={null}
                          options={documentOptions}
                        >
                          <Page
                            pageNumber={currentPage}
                            width={pdfWidth}
                            scale={zoomScale}
                            renderTextLayer={false}
                            renderAnnotationLayer={false}
                            canvasBackground="white"
                          />
                        </Document>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-400 text-sm text-center p-4">
                      <div>
                        <FileText className="h-12 w-12 mx-auto mb-3 opacity-50" />
                        Bewegen Sie die Maus über das Dokument
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t bg-gray-50 rounded-b-xl">
          {/* Page Navigation */}
          <div className="flex items-center gap-2">
            <button
              onClick={goToPrevPage}
              disabled={currentPage <= 1}
              className="p-2 text-gray-600 hover:bg-gray-200 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <span className="text-sm text-gray-600 min-w-[100px] text-center">
              Seite {currentPage} von {numPages}
            </span>
            <button
              onClick={goToNextPage}
              disabled={currentPage >= numPages}
              className="p-2 text-gray-600 hover:bg-gray-200 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>

          {/* Download Button */}
          <button
            onClick={handleDownload}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Download className="h-4 w-4" />
            Download
          </button>
        </div>
      </div>
    </div>
  )
}
