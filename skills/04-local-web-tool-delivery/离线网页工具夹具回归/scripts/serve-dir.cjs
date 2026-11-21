// One-shot CORS static server for test fixtures only. Binds 127.0.0.1, never a public interface.
// usage: node serve-dir.cjs <rootDir> [port]
const http = require('http');
const fs = require('fs');
const path = require('path');

const root = path.resolve(process.argv[2] || '.');
const preferred = Number(process.argv[3] || 0);
if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) {
  console.log('FAIL root is not a directory: ' + root);
  process.exit(2);
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  '.xls': 'application/vnd.ms-excel',
  '.png': 'image/png',
};

function send(res, status, body, headers) {
  res.writeHead(status, Object.assign({ 'Cache-Control': 'no-store', 'Access-Control-Allow-Origin': '*' }, headers || {}));
  res.end(body);
}

const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '');
  const abs = path.resolve(root, rel || '.');
  if (abs !== root && !abs.startsWith(root + path.sep)) {
    send(res, 403, 'forbidden', { 'Content-Type': 'text/plain; charset=utf-8' });
    console.log('403 ' + req.url);
    return;
  }
  fs.readFile(abs, (err, buf) => {
    if (err) {
      send(res, 404, 'not found: ' + rel, { 'Content-Type': 'text/plain; charset=utf-8' });
      console.log('404 ' + req.url);
      return;
    }
    send(res, 200, buf, { 'Content-Type': MIME[path.extname(abs).toLowerCase()] || 'application/octet-stream' });
    console.log('200 ' + req.url + ' ' + buf.length + 'B');
  });
});

function listen(port, attempts) {
  server.once('error', (err) => {
    if (err.code === 'EADDRINUSE' && attempts > 0) {
      console.log('BUSY ' + port + ' -> trying ' + (port + 1));
      listen(port + 1, attempts - 1);
      return;
    }
    console.log('FAIL ' + err.code + ' ' + err.message);
    process.exit(2);
  });
  server.listen(port, '127.0.0.1', () => {
    console.log('READY http://127.0.0.1:' + port + '/ root=' + root);
  });
}

server.listen(preferred || 8790, '127.0.0.1');

process.on('SIGINT', () => process.exit(0));
process.on('SIGTERM', () => process.exit(0));
