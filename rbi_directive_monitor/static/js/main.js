// RBI Master Directives Monitor - Main JavaScript

// Global configuration
const API_BASE = '/api';

// Format timestamp for display
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-IN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Manual scrape trigger
async function manualScrape() {
    try {
        const btn = event.target;
        btn.disabled = true;
        btn.textContent = 'Scraping...';

        const response = await fetch(`${API_BASE}/manual-scrape`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            alert('Scraping initiated! This may take a few moments.');
            setTimeout(() => location.reload(), 3000);
        } else {
            alert('Error initiating scrape. Please try again.');
            btn.disabled = false;
            btn.textContent = 'Check Now';
        }
    } catch (error) {
        console.error('Scrape error:', error);
        alert('Error: ' + error.message);
        btn.disabled = false;
        btn.textContent = 'Check Now';
    }
}

// Filter table by search term
function filterTable() {
    const input = document.getElementById("search-box");
    if (!input) return;

    const filter = input.value.toUpperCase();
    const table = document.getElementById("directives-table");
    if (!table) return;

    const rows = table.getElementsByTagName("tr");

    for (let i = 1; i < rows.length; i++) {
        const row = rows[i];
        const text = row.textContent || row.innerText;
        row.style.display = text.toUpperCase().indexOf(filter) > -1 ? "" : "none";
    }
}

// Load status and update display
async function loadStatus() {
    try {
        const response = await fetch(`${API_BASE}/status`);
        if (response.ok) {
            const data = await response.json();
            updateStatusDisplay(data);
        }
    } catch (error) {
        console.error('Status load error:', error);
    }
}

function updateStatusDisplay(status) {
    // Update status elements if they exist
    const schedulerStatus = document.getElementById('scheduler-status');
    if (schedulerStatus && status.scheduler) {
        schedulerStatus.textContent = status.scheduler.running ? 'Running' : 'Stopped';
    }

    const nextRun = document.getElementById('next-run');
    if (nextRun && status.scheduler && status.scheduler.next_run) {
        nextRun.textContent = formatDate(status.scheduler.next_run);
    }
}

// Export functionality (if needed)
function exportToCSV() {
    const table = document.querySelector('.directives-table');
    if (!table) return;

    let csv = [];
    const rows = table.querySelectorAll('tr');

    rows.forEach(row => {
        const cols = row.querySelectorAll('td, th');
        csv.push(Array.from(cols).map(col => col.textContent).join(','));
    });

    downloadCSV(csv.join('\n'), 'directives.csv');
}

function downloadCSV(csv, filename) {
    const csvFile = new Blob([csv], { type: 'text/csv' });
    const downloadLink = document.createElement('a');
    downloadLink.href = URL.createObjectURL(csvFile);
    downloadLink.download = filename;
    document.body.appendChild(downloadLink);
    downloadLink.click();
    downloadLink.remove();
}

// Search functionality
function searchDirectives() {
    const query = document.getElementById('search-input').value;
    if (query.length < 3) return;

    fetch(`${API_BASE}/directives/search?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => displaySearchResults(data))
        .catch(error => console.error('Search error:', error));
}

function displaySearchResults(directives) {
    const resultsDiv = document.getElementById('search-results');
    if (!resultsDiv) return;

    if (directives.length === 0) {
        resultsDiv.innerHTML = '<p>No directives found.</p>';
        return;
    }

    let html = '<table class="directives-table"><thead><tr><th>Date</th><th>Title</th><th>Category</th><th>Score</th></tr></thead><tbody>';

    directives.forEach(d => {
        html += `<tr><td>${d.publication_date.split('T')[0]}</td><td>${d.title}</td><td>${d.category}</td><td>${d.similarity_score.toFixed(2)}</td></tr>`;
    });

    html += '</tbody></table>';
    resultsDiv.innerHTML = html;
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadStatus();

    // Auto-refresh status every 5 minutes
    setInterval(loadStatus, 5 * 60 * 1000);
});

// Utility: Pretty print JSON
function prettyJSON(obj) {
    return JSON.stringify(obj, null, 2);
}

// Utility: Get query parameter from URL
function getQueryParam(param) {
    const params = new URLSearchParams(window.location.search);
    return params.get(param);
}

// Utility: Confirm before action
function confirmAction(message) {
    return confirm(message);
}
