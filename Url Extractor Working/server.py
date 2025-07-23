import re
import os
import asyncio
import aiohttp
import csv
import json
from io import StringIO
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# Regex pattern to extract URLs
URL_PATTERN = r'https?://[^\s<>"]+|www\.[^\s<>"]+'

async def fetch_status(session, url, semaphore):
    """Fetch the status of a URL asynchronously with limited concurrency."""
    async with semaphore:
        try:
            async with session.get(url, timeout=5) as response:
                return url, response.status
        except aiohttp.ClientError:
            return url, "error"
        except asyncio.TimeoutError:
            return url, "timeout"
        except Exception as e:
            return url, f"error: {str(e)}"

async def check_urls(urls):
    """Check URLs in parallel using async requests with concurrency control."""
    semaphore = asyncio.Semaphore(10)  # Limit to 10 concurrent requests
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_status(session, url, semaphore) for url in urls]
        results = await asyncio.gather(*tasks)

    # Categorize results
    status_results = {
        "200": [],
        "301_302": [],
        "403": [],
        "404": [],
        "500+": [],
        "error": []
    }

    for url, status in results:
        if status == 200:
            status_results["200"].append(url)
        elif status in [301, 302]:
            status_results["301_302"].append(url)
        elif status == 403:
            status_results["403"].append(url)
        elif status == 404:
            status_results["404"].append(url)
        elif isinstance(status, int) and status >= 500:
            status_results["500+"].append(url)
        else:
            status_results["error"].append(url)

    return status_results

def generate_csv(data):
    """Convert status results into CSV format."""
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["URL", "Status"])
    for status, urls in data.items():
        for url in urls:
            writer.writerow([url, status])
    return output.getvalue()

def generate_json(data):
    """Convert status results into JSON format."""
    return json.dumps(data, indent=4)

@app.route("/")
def index():
    """Serve the frontend page."""
    return render_template("index.html")

@app.route("/extract", methods=["POST"])
def extract_urls():
    """Extract URLs from uploaded file(s) and check status asynchronously."""
    if "files" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    files = request.files.getlist("files")
    if not files or all(file.filename == "" for file in files):
        return jsonify({"error": "No selected file"}), 400

    # Read file content and extract URLs
    urls = []
    for file in files:
        text = file.read().decode("utf-8")
        urls.extend(re.findall(URL_PATTERN, text))

    # Remove duplicates
    unique_urls = list(set(urls))

    # Run async function safely inside Flask
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    status_results = loop.run_until_complete(check_urls(unique_urls))

    # Generate CSV and JSON data
    csv_data = generate_csv(status_results)
    json_data = generate_json(status_results)

    return jsonify({
        "urls": urls,
        "unique_urls": unique_urls,
        "status_results": status_results,
        "csv_data": csv_data,
        "json_data": json_data
    })

if __name__ == "__main__":
    app.run(debug=True)