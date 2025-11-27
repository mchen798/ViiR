UPLOAD_DIR = Path("/workspace")
@app.get("/upload", response_class=HTMLResponse)
def upload_page():
    return """
<!doctype html>
<html>
  <body>
    <h3>Upload to /workspace</h3>
    <input id="f" type="file" />
    <button onclick="start()">Upload</button>
    <div id="p"></div>
    <script>
      function start() {
        const f = document.getElementById('f').files[0];
        if (!f) { alert('pick a file'); return; }
        const form = new FormData();
        form.append('file', f, f.name);
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/upload');
        xhr.upload.onprogress = (e)=> {
          if (e.lengthComputable) {
            const pct = (e.loaded / e.total * 100).toFixed(1);
            document.getElementById('p').innerText = `${pct}% (${(e.loaded/1024/1024).toFixed(1)} MiB)`;
          }
        };
        xhr.onload = ()=> { document.getElementById('p').innerText += '\\n' + xhr.responseText; };
        xhr.onerror = ()=> { document.getElementById('p').innerText += '\\nError'; };
        xhr.send(form);
      }
    </script>
  </body>
</html>
"""