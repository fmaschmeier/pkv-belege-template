import { pdfjs } from 'react-pdf'

// Configure PDF.js worker
// Bundled with the app (no CDN): Vite copies the worker from pdfjs-dist and rewrites this URL
pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()
