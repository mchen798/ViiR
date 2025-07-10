/* Mock functionality for ViiR web prototype */

function analyzeData() {
    const input = document.getElementById('analysis-input').value;
    if (!input.trim()) {
        alert('Please provide input data.');
        return;
    }
    const wordCount = input.trim().split(/\s+/).length;
    const result = `Sample analysis complete.\nWord count: ${wordCount}`;
    document.getElementById('results').textContent = result;
}

function addNote() {
    const noteText = document.getElementById('note-text').value;
    if (!noteText.trim()) return;
    const notes = document.getElementById('notes');
    const item = document.createElement('li');
    item.textContent = noteText;
    notes.appendChild(item);
    document.getElementById('note-text').value = '';
}

function exportCSV() {
    const csvContent = 'data:text/csv;charset=utf-8,Sample,Value\nA,1\nB,2';
    const encoded = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encoded);
    link.setAttribute('download', 'result.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function renderChart() {
    const canvas = document.getElementById('chart');
    const ctx = canvas.getContext('2d');
    const data = [12, 19, 3, 5];
    const labels = ['A', 'B', 'C', 'D'];
    const width = canvas.width / data.length;
    ctx.fillStyle = '#3867d6';
    data.forEach((val, i) => {
        const x = i * width + 10;
        const y = canvas.height - val * 5;
        const h = val * 5;
        ctx.fillRect(x, y, width - 20, h);
        ctx.fillText(labels[i], x + (width - 20) / 2 - 5, canvas.height - 5);
    });
}


function renderDEChart() {
    const canvas = document.getElementById('de-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const labels = ['gene1', 'gene2', 'gene3', 'gene4', 'gene5'];
    const data = [5, 12, 8, 3, 9];
    const width = canvas.width / data.length;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#e17055';
    data.forEach((val, i) => {
        const x = i * width + 10;
        const y = canvas.height - val * 5;
        const h = val * 5;
        ctx.fillRect(x, y, width - 20, h);
        ctx.fillText(labels[i], x + (width - 20) / 2 - 10, canvas.height - 5);
    });
}

function resetPipelineSteps() {
    document.querySelectorAll('#pipeline-steps li').forEach(li => {
        li.classList.remove('done');
        li.classList.add('pending');
    });
}

function markPipelineDone() {
    document.querySelectorAll('#pipeline-steps li').forEach(li => {
        li.classList.remove('pending');
        li.classList.add('done');
    });
}

document.addEventListener('DOMContentLoaded', renderChart);

// Submit pipeline run via AJAX
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('run-form');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const outputPre = document.getElementById('run-output');
        resetPipelineSteps();
        outputPre.textContent = 'Running...';
        const formData = new FormData(form);
        try {
            const resp = await fetch('/runner', {
                method: 'POST',
                body: formData,
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            const data = await resp.json();
            outputPre.textContent = data.output || 'No output';
            markPipelineDone();
            renderDEChart();
        } catch (err) {
            outputPre.textContent = 'Failed to start job.';
        }
    });
});

