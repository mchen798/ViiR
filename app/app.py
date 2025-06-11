from flask import Flask, request, render_template, render_template_string, redirect, url_for
import os
import subprocess
import uuid

UPLOAD_DIR = os.environ.get("VIIR_UPLOAD_DIR", "/data")

app = Flask(__name__, static_folder='static', template_folder='templates')

HTML_FORM = """
<!doctype html>
<title>ViiR Runner</title>
<h1>Run ViiR</h1>
<form method=post enctype=multipart/form-data>
  YAML config file: <input type=file name=config><br>
  FASTQ list file: <input type=file name=fastq_list><br>
  Output directory: <input type=text name=out value="run_{{uid}}"><br>
  <input type=submit value="Run">
</form>
<pre>{{output}}</pre>
"""

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/runner', methods=['GET', 'POST'])
def runner():
    output = ''
    uid = uuid.uuid4().hex[:8]
    if request.method == 'POST':
        job_dir = os.path.join(UPLOAD_DIR, uid)
        os.makedirs(job_dir, exist_ok=True)

        config_f = request.files.get('config')
        fastq_f = request.files.get('fastq_list')
        out_dir = request.form.get('out') or f'run_{uid}'
        args = []

        if config_f and config_f.filename:
            config_path = os.path.join(job_dir, config_f.filename)
            config_f.save(config_path)
            args = ['viir', '--config', config_path]
        elif fastq_f and fastq_f.filename:
            fastq_path = os.path.join(job_dir, fastq_f.filename)
            fastq_f.save(fastq_path)
            out_path = os.path.join(job_dir, out_dir)
            args = ['viir', '-l', fastq_path, '-o', out_path]
        else:
            output = 'No configuration or FASTQ list provided.'
            return render_template_string(HTML_FORM, output=output, uid=uid)

        try:
            proc = subprocess.run(args, capture_output=True, text=True, check=True)
            output = proc.stdout + '\n' + proc.stderr
        except subprocess.CalledProcessError as e:
            output = e.stdout + '\n' + e.stderr

    return render_template_string(HTML_FORM, output=output, uid=uid)


@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    if not file or not file.filename:
        return redirect(url_for('home'))
    uid = uuid.uuid4().hex[:8]
    job_dir = os.path.join(UPLOAD_DIR, uid)
    os.makedirs(job_dir, exist_ok=True)
    file.save(os.path.join(job_dir, file.filename))
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
