import { pdfjs } from 'react-pdf'

// Configure PDF.js worker
// This uses the CDN version which is most reliable with Vite
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`
